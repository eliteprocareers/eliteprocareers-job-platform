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
from eliteprocareers.organizations.repository import OrganizationRepository

router = APIRouter(prefix="/organizations", tags=["organizations"])

_STATUS_RE = re.compile(r"failed \((\d+)\)")


def _friendly_supabase_error(exc: SupabaseError, fallback_status: int) -> HTTPException:
    """Turns a SupabaseError from a raise-exception'd RPC (or an RLS
    policy denial) into an HTTPException with the real reason, instead
    of letting main.py's global handler flatten every SupabaseError
    into a generic 502 "Upstream data error". Postgres exceptions
    raised inside our SECURITY DEFINER functions (create_organization_
    with_owner, accept_organization_invite) carry a real, safe-to-show
    message -- e.g. "You already belong to an organization." -- that's
    worth surfacing, unlike a raw RLS/constraint error.
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


@router.post("", response_model=Organization, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: CreateOrganizationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Organization:
    """Creates a new organization with the caller as owner. Atomic --
    see create_organization_with_owner() in migration 0010. Fails with
    a 409 if the caller already belongs to an org (one org per user,
    for now -- see that migration's comments on why).
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
    missing profile as "show the CV upload flow".
    """
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You don't belong to an organization yet.",
        )
    org = OrganizationRepository(current_user.db).get_organization(current_user.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return org


def _require_org(current_user: CurrentUser) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You don't belong to an organization yet.",
        )
    return current_user.organization_id


def _require_admin_role(current_user: CurrentUser, organization_id: UUID) -> None:
    """Pre-check for a clean 403 before hitting the DB, on top of (not
    instead of) the RLS is_org_admin() policy that enforces this for
    real -- same defense-in-depth as every other admin-gated write in
    this API relying on RLS as the actual source of truth.
    """
    rows = current_user.db.select(
        "organization_members",
        params={
            "select": "role",
            "organization_id": f"eq.{organization_id}",
            "user_id": f"eq.{current_user.id}",
        },
    )
    if not rows or rows[0]["role"] not in (MemberRole.owner.value, MemberRole.admin.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization owner or admin can do this.",
        )


@router.get("/members", response_model=list[OrganizationMember])
def list_members(current_user: CurrentUser = Depends(get_current_user)) -> list[OrganizationMember]:
    organization_id = _require_org(current_user)
    return OrganizationRepository(current_user.db).list_members(organization_id)


def _require_owner_role(current_user: CurrentUser, organization_id: UUID) -> None:
    """Stricter than _require_admin_role -- used specifically for
    operations touching another member's 'owner' status. RLS
    (is_org_admin, migration 0007) treats owner and admin as equally
    privileged for these tables, which would let an admin remove or
    demote an owner -- deliberately narrowed here at the app layer,
    since that's a real privilege-escalation-adjacent gap, not a
    hypothetical one. Not a fix to the RLS policy itself (that's a
    bigger, separate decision) -- just doesn't let this app surface
    make it worse.
    """
    rows = current_user.db.select(
        "organization_members",
        params={
            "select": "role",
            "organization_id": f"eq.{organization_id}",
            "user_id": f"eq.{current_user.id}",
        },
    )
    if not rows or rows[0]["role"] != MemberRole.owner.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization owner can do this.",
        )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> None:
    """Admin/owner only (RLS is_org_admin). Two guards on top of that,
    checked before the delete, not left to RLS alone:
      - the org's last owner can never be removed (would orphan it --
        nothing in the schema stops that otherwise, confirmed by
        reading is_org_admin()'s definition directly).
      - removing an owner at all requires the caller to themselves be
        an owner (see _require_owner_role) -- an admin can remove
        members and other admins, not owners.
    """
    organization_id = _require_org(current_user)
    _require_admin_role(current_user, organization_id)

    repo = OrganizationRepository(current_user.db)
    target_role = repo.get_member_role(organization_id, member_id)
    if target_role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if target_role == MemberRole.owner.value:
        _require_owner_role(current_user, organization_id)
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
    """Same guard shape as remove_member: admin/owner can change a
    member's or admin's role; only an owner can grant or revoke
    'owner' status on someone else, and the last owner can never be
    demoted away from 'owner' (checked whether it's a self-demotion or
    someone else doing it).
    """
    organization_id = _require_org(current_user)
    _require_admin_role(current_user, organization_id)

    repo = OrganizationRepository(current_user.db)
    target_role = repo.get_member_role(organization_id, member_id)
    if target_role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    involves_owner = target_role == MemberRole.owner.value or payload.role == MemberRole.owner
    if involves_owner:
        _require_owner_role(current_user, organization_id)

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
    """Owner/admin only. There's no email-sending integration yet --
    the response's `token` is the one and only time the invite link is
    exposed; the admin copies and sends it manually. Share it as
    `<frontend_url>/invites/accept?token=<token>`.
    """
    organization_id = _require_org(current_user)
    _require_admin_role(current_user, organization_id)
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
    organization_id = _require_org(current_user)
    _require_admin_role(current_user, organization_id)
    return OrganizationRepository(current_user.db).list_invites(organization_id)


@router.delete("/invites/{invite_id}", response_model=OrganizationInvite)
def revoke_invite(
    invite_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> OrganizationInvite:
    organization_id = _require_org(current_user)
    _require_admin_role(current_user, organization_id)
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
