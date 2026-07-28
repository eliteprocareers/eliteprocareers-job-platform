"""
Centralized permission system for the 4-tier role model
(owner/admin/manager/staff -- migration 0014).

This is the single source of truth for "what can this role do" across
the whole app. Routers should call require_permission() (or
has_permission() for a soft check that doesn't raise) instead of
hand-rolling role comparisons -- the two pre-existing hand-rolled
checks this replaces, _require_admin_role and _require_owner_role in
api/routers/organizations.py, are being migrated to use this (see that
file), not left as a second, competing source of truth.

Design: RLS still owns tenant isolation (can this caller see/touch
this organization_id at all -- is_org_member()/is_org_admin(),
migration 0007) and orphan-prevention invariants (last-owner guards,
migrations 0007/0013) stay exactly where they are, as integrity rules
rather than permissions. This module owns "given the caller is already
inside their own org, what are they allowed to do" -- role-based
authorization, not row-level tenant isolation. The two work together:
RLS answers "whose data is this", this module answers "does this
person's role let them do X to it."

Resource coverage matches what this platform actually has (confirmed
against the real schema, not a generic template): org administration,
tracks, applications, documents, matches. Nothing here references
concepts (inventory, staff scheduling, reports) that don't exist in
this codebase.
"""

from enum import Enum
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from eliteprocareers.api.dependencies import CurrentUser


class Permission(str, Enum):
    # Organization administration
    manage_org_settings = "manage_org_settings"  # rename, org_type
    manage_owners = "manage_owners"  # grant/revoke 'owner' on someone else
    manage_members = "manage_members"  # remove members, change non-owner roles
    view_members = "view_members"
    manage_invites = "manage_invites"  # create/revoke invites

    # Tracks (job-search tracks -- profiles/track_repository.py)
    manage_tracks = "manage_tracks"
    view_tracks = "view_tracks"

    # Applications
    manage_applications = "manage_applications"
    view_applications = "view_applications"

    # Documents (generated CVs/cover letters)
    manage_documents = "manage_documents"
    view_documents = "view_documents"

    # Matches (job-matching results, triggering match runs)
    manage_matches = "manage_matches"
    view_matches = "view_matches"


# Single source of truth: every role's full permission set, written
# out explicitly rather than derived by subtraction/addition from a
# neighboring tier -- an explicit table is easier to audit at a glance
# than "manager = admin minus X plus Y" chains that drift over time.
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": frozenset(Permission),  # everything
    "admin": frozenset(Permission) - {Permission.manage_owners},
    "manager": frozenset(
        {
            Permission.view_members,
            Permission.manage_tracks,
            Permission.view_tracks,
            Permission.manage_applications,
            Permission.view_applications,
            Permission.manage_documents,
            Permission.view_documents,
            Permission.manage_matches,
            Permission.view_matches,
        }
    ),
    "staff": frozenset(
        {
            Permission.view_members,
            Permission.view_tracks,
            Permission.view_applications,
            Permission.view_documents,
            Permission.view_matches,
        }
    ),
}


def has_permission(role: str | None, permission: Permission) -> bool:
    """Soft check -- returns False rather than raising, for call sites
    that want to branch (e.g. deciding what to include in a response)
    rather than reject the whole request. role=None (no org
    membership at all) has no permissions.
    """
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(current_user: "CurrentUser", permission: Permission) -> None:
    """Hard check -- the one routers should actually call. Raises 404
    if the caller has no organization at all (nothing to check
    permissions within), or 403 with the specific permission named in
    the message if their role doesn't include it. This is the
    replacement for api/routers/organizations.py's old
    _require_admin_role/_require_owner_role -- both are now thin
    wrappers around this (see that file), not a second, competing
    definition of who's allowed to do what.
    """
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You don't belong to an organization yet.",
        )
    if not has_permission(current_user.organization_role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role doesn't have the '{permission.value}' permission.",
        )
