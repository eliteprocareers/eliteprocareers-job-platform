import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.schemas import (
    AcceptInviteRequest,
    CreateInviteRequest,
    CreateOrganizationRequest,
    UpdateMemberRoleRequest,
    UpdateOrganizationRequest,
)
from eliteprocareers.db.client import SupabaseError
from eliteprocareers.organizations.models import (
    InvitePreview,
    MemberRole,
    Organization,
    OrganizationInvite,
    OrganizationInviteCreated,
    OrganizationMember,
)
from eliteprocareers.organizations.permissions import Permission, require_permission
from eliteprocareers.organizations.repository import OrganizationRepository

router = APIRouter(prefix="/organizations", tags=["organizations"])

_STATUS_RE = re.compile(r"failed \((\d+)\)")


def _friendly_supabase_error(exc: SupabaseError, fallback_status: int) -> HTTPException:
    """Turns a SupabaseError from a raise-exception'd RPC (or an RLS
    policy denial) into an HTTPException with the real reason, instead
    of letting main.py's global handler flatten every SupabaseError
    into a generic 502 "Upstream data error". Postgres exceptions
    raised inside our SECURITY DEFINER functions (create_organization_
    with_owner, accept_organization_invite, leave_organization) carry
    a real, safe-to-show message -- e.g. "You already belong to an
    organization." -- that's worth surfacing, unlike a raw RLS/
    constraint error.
    """
    raw = str(exc)
    http_status = fallback_status
    status_match = _STATUS_RE.search(raw)
    if status_match:
        code = int(status_match.group(1))
        if code == 403:
            http_status = status.HTTP_403_FORBIDDEN

    message = raw
    body_start = raw.find("): ")
    if body_start != -1:
        body_text = raw[body_start + 3 :]
        try:
            parsed = json.loads(body_text)
            message = parsed.get("message", body_text)
        except (json.JSONDecodeError, AttributeError):
            message = body_text

    return HTTPException(status_code=http_status, detail=message)


def _require_org(current_user: CurrentUser) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You don't belong to an organization yet.",
        )
    return current_user.organization_id


@router.post("", response_model=Organization, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: CreateOrganizationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Organization:
    """Creates a new organization with the caller as owner. Atomic --
    see create_organization_with_owner() in migration 0010. Fails with
    a 409 if the caller already belongs to an org (one org per user,
    for now -- see that migration's comments on why). No permission
    check here -- this is how someone *gets* a role in the first
    place, there's nothing to check permissions against yet.
    """
    try:
        return OrganizationRepository(current_user.db).create_organization(
            name=payload.name, org_type=payload.org_type.value
        )
    except SupabaseError as exc:
        raise _friendly_supabase_error(exc, fallback_status=status.HTTP_409_CONFLICT) from exc


@router.get("/me", response_model=Organization)
def get_my_organization(current_user: CurrentUser = Depends(get_current_user)) -> Organization:
    """The authenticated user's organization. 404 if they don't belong
    to one yet -- the frontend should treat that as "show the create-
    organization flow", same as profile.py's get_my_profile treats a
    missing profile as "show the CV upload flow". No permission check
    beyond org membership itself -- every role can see their own org.
    """
    organization_id = _require_org(current_user)
    org = OrganizationRepository(current_user.db).get_organization(organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return org


@router.patch("", response_model=Organization)
def update_organization(
    payload: UpdateOrganizationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Organization:
    """Requires manage_org_settings (owner/admin -- see
    organizations/permissions.py's ROLE_PERMISSIONS). RLS
    (is_org_admin) has permitted this since migration 0007's UPDATE
    policy on organizations -- just never had an application endpoint
    calling it until now.
    """
    require_permission(current_user, Permission.manage_org_settings)
    organization_id = _require_org(current_user)
    org_type_value = payload.org_type.value if payload.org_type is not None else None
    updated = OrganizationRepository(current_user.db).update_organization(
        organization_id, name=payload.name, org_type=org_type_value
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return updated


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_organization(current_user: CurrentUser = Depends(get_current_user)) -> None:
    """Self-service, no particular permission required beyond being a
    member at all -- this is a member removing themselves, not
    managing someone else. See leave_organization() in migration 0013
    for why this needed its own RPC rather than reusing DELETE
    /organizations/members/{id}: the DELETE RLS policy on
    organization_members is admin-only, so a plain staff/manager
    member has no other way to leave at all.
    """
    try:
        OrganizationRepository(current_user.db).leave_organization()
    except SupabaseError as exc:
        raise _friendly_supabase_error(exc, fallback_status=status.HTTP_409_CONFLICT) from exc


@router.get("/members", response_model=list[OrganizationMember])
def list_members(current_user: CurrentUser = Depends(get_current_user)) -> list[OrganizationMember]:
    require_permission(current_user, Permission.view_members)
    organization_id = _require_org(current_user)
    return OrganizationRepository(current_user.db).list_members(organization_id)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> None:
    """Requires manage_members (owner/admin). Two guards on top of
    that, checked before the delete, not left to RLS or the permission
    check alone:
      - the org's last owner can never be removed (would orphan it --
        nothing in the schema stops that otherwise, confirmed by
        reading is_org_admin()'s definition directly).
      - removing an owner at all requires manage_owners (owner-only --
        see organizations/permissions.py; RLS's is_org_admin() treats
        owner and admin as equally privileged for this table, which
        would let an admin remove an owner if this app-layer check
        didn't narrow it).
    """
    require_permission(current_user, Permission.manage_members)
    organization_id = _require_org(current_user)

    repo = OrganizationRepository(current_user.db)
    target_role = repo.get_member_role(organization_id, member_id)
    if target_role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if target_role == MemberRole.owner.value:
        require_permission(current_user, Permission.manage_owners)
        if repo.count_owners(organization_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Can't remove the organization's last owner.",
            )

    repo.remove_member(organization_id, member_id)


@router.patch("/members/{member_id}/role", response_model=OrganizationMember)
def update_member_role(
    member_id: UUID,
    payload: UpdateMemberRoleRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> OrganizationMember:
    """Same guard shape as remove_member: manage_members (owner/admin)
    can change a staff/manager/admin's role; manage_owners (owner-only)
    is required to grant or revoke 'owner' status on someone else, and
    the last owner can never be demoted away from 'owner' (checked
    whether it's a self-demotion or someone else doing it).
    """
    require_permission(current_user, Permission.manage_members)
    organization_id = _require_org(current_user)

    repo = OrganizationRepository(current_user.db)
    target_role = repo.get_member_role(organization_id, member_id)
    if target_role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    involves_owner = target_role == MemberRole.owner.value or payload.role == MemberRole.owner
    if involves_owner:
        require_permission(current_user, Permission.manage_owners)

    if target_role == MemberRole.owner.value and payload.role != MemberRole.owner:
        if repo.count_owners(organization_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Can't demote the organization's last owner.",
            )

    updated = repo.update_member_role(organization_id, member_id, payload.role.value)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    return updated


@router.post("/invites", response_model=OrganizationInviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: CreateInviteRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> OrganizationInviteCreated:
    """Requires manage_invites (owner/admin). There's no email-sending
    integration yet -- the response's `token` is the one and only time
    the invite link is exposed; the admin copies and sends it manually.
    Share it as `<frontend_url>/invites/accept?token=<token>`.
    """
    require_permission(current_user, Permission.manage_invites)
    organization_id = _require_org(current_user)
    try:
        return OrganizationRepository(current_user.db).create_invite(
            organization_id=organization_id,
            email=payload.email,
            role=payload.role.value,
            invited_by=current_user.id,
        )
    except SupabaseError as exc:
        raise _friendly_supabase_error(exc, fallback_status=status.HTTP_400_BAD_REQUEST) from exc


@router.get("/invites", response_model=list[OrganizationInvite])
def list_invites(current_user: CurrentUser = Depends(get_current_user)) -> list[OrganizationInvite]:
    require_permission(current_user, Permission.manage_invites)
    organization_id = _require_org(current_user)
    return OrganizationRepository(current_user.db).list_invites(organization_id)


@router.delete("/invites/{invite_id}", response_model=OrganizationInvite)
def revoke_invite(
    invite_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> OrganizationInvite:
    require_permission(current_user, Permission.manage_invites)
    organization_id = _require_org(current_user)
    invite = OrganizationRepository(current_user.db).revoke_invite(invite_id, organization_id)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    return invite


@router.get("/invites/preview/{token}", response_model=InvitePreview)
def preview_invite(token: str) -> InvitePreview:
    """No auth required -- this is the "you've been invited to X" page
    the invitee sees before logging in. Backed by get_invite_preview(),
    an anon-callable SECURITY DEFINER function that exposes only the
    org name, the invited email, role, status, and expiry -- nothing
    else about the organization.
    """
    preview = OrganizationRepository.get_invite_preview(token)
    if preview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    return preview


@router.post("/invites/accept", response_model=Organization)
def accept_invite(
    payload: AcceptInviteRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Organization:
    """The invitee must already be logged in (create an account first
    via POST /auth/signup if they don't have one -- there is deliberately
    no "sign up and accept in one step" endpoint yet, flagged as a
    follow-up). Atomic -- see accept_organization_invite() in migration
    0010: validates the invite (pending, not expired, email matches
    the caller's verified JWT email) and inserts membership in one
    transaction.
    """
    try:
        repo = OrganizationRepository(current_user.db)
        organization_id = repo.accept_invite(payload.token)
        org = repo.get_organization(organization_id)
    except SupabaseError as exc:
        raise _friendly_supabase_error(exc, fallback_status=status.HTTP_400_BAD_REQUEST) from exc
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found."
        )
    return org
