"""
Repository for organizations, membership, and invites.

Split by which auth path each operation needs (see migration 0010 for
the full reasoning):

  - Creating an org and accepting an invite each cross a membership
    boundary that RLS can't authorize on its own (you can't prove
    you're an org's admin before you're in it) -- both go through
    SECURITY DEFINER Postgres functions via db.rpc(), called with the
    user's own token so auth.uid()/auth.jwt() inside the function still
    resolve to that specific user. Never called with a service_role
    client -- that would defeat the point of tying the operation to a
    specific authenticated caller.
  - Everything else an already-a-member admin does (view org, list
    members, create/list/revoke invites) is a normal RLS-checked
    select/insert/update via the user-scoped client, same as every
    other repository in this codebase.
  - get_invite_preview is the one read that must work for someone who
    isn't authenticated yet (they're looking at an invite link before
    signing in) -- called with an anon-key client, never service_role.
"""

from uuid import UUID

from eliteprocareers.config import settings
from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.organizations.models import (
    CandidateAssignment,
    InvitePreview,
    Organization,
    OrganizationInvite,
    OrganizationInviteCreated,
    OrganizationMember,
)


class OrganizationRepository:
    ORG_TABLE = "organizations"
    MEMBER_TABLE = "organization_members"
    INVITE_TABLE = "organization_invites"
    ASSIGNMENT_TABLE = "organization_candidate_assignments"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Organization creation / lookup
    # ------------------------------------------------------------------

    def create_organization(self, name: str, org_type: str = "individual") -> Organization:
        """Atomic: creates the org and seats the caller as owner in one
        transaction, via create_organization_with_owner(). Raises
        SupabaseError (surfaced as a 502 by main.py's handler, or the
        router should catch it explicitly for a cleaner 400/409 -- see
        organizations.py router) if the caller already belongs to an
        org, or if p_name is blank.
        """
        row = self.db.rpc(
            "create_organization_with_owner",
            {"p_name": name, "p_org_type": org_type},
        )
        return Organization.model_validate(row)

    def get_organization(self, organization_id: UUID) -> Organization | None:
        rows = self.db.select(
            self.ORG_TABLE, params={"select": "*", "id": f"eq.{organization_id}"}
        )
        if not rows:
            return None
        return Organization.model_validate(rows[0])

    def update_organization(
        self,
        organization_id: UUID,
        name: str | None,
        org_type: str | None,
        sharing_mode: str | None = None,
    ) -> Organization | None:
        """RLS (is_org_admin, migration 0007) already gates this --
        the UPDATE policy on organizations existed since 0007 but,
        like the members DELETE/UPDATE policies, was never wired up
        in application code until now. Only includes fields that were
        actually provided (partial update), so leaving a field out of
        the request doesn't clobber it with a default. sharing_mode
        added in migration 0015 -- the org-wide opt-in to full
        candidate-data sharing instead of assigned_only.
        """
        data: dict = {}
        if name is not None:
            data["name"] = name
        if org_type is not None:
            data["org_type"] = org_type
        if sharing_mode is not None:
            data["sharing_mode"] = sharing_mode
        if not data:
            return self.get_organization(organization_id)
        rows = self.db.update(self.ORG_TABLE, data=data, params={"id": f"eq.{organization_id}"})
        if not rows:
            return None
        return Organization.model_validate(rows[0])

    def leave_organization(self) -> UUID:
        """Atomic -- see leave_organization() in migration 0013. Exists
        because the DELETE RLS policy on organization_members only
        permits is_org_admin(), which means a plain member couldn't
        remove themselves at all otherwise -- confirmed by reading
        that policy directly, not assumed. Enforces the same
        last-owner orphan guard as the admin-driven remove/demote
        paths. Raises SupabaseError with the function's own message if
        the caller isn't a member, or is the org's last owner.
        """
        organization_id = self.db.rpc("leave_organization", {})
        return UUID(organization_id)

    # ------------------------------------------------------------------
    # Candidate assignments (migration 0015 -- assigned_only sharing)
    # ------------------------------------------------------------------

    def create_assignment(
        self, organization_id: UUID, candidate_user_id: UUID, assigned_to: UUID, assigned_by: UUID
    ) -> CandidateAssignment:
        """RLS-gated to owners/admins (manage_assignments permission,
        checked at the router level too -- same defense-in-depth as
        everywhere else in this module). The unique constraint on
        (organization_id, candidate_user_id, assigned_to) means
        assigning the same candidate to the same person twice is a
        no-op failure, not a duplicate row -- surfaced as a
        SupabaseError, same handling as every other constraint
        violation in this repository.
        """
        payload = {
            "organization_id": str(organization_id),
            "candidate_user_id": str(candidate_user_id),
            "assigned_to": str(assigned_to),
            "assigned_by": str(assigned_by),
        }
        rows = self.db.insert(self.ASSIGNMENT_TABLE, payload)
        return CandidateAssignment.model_validate(rows[0])

    def list_assignments(self, organization_id: UUID) -> list[CandidateAssignment]:
        """No extra filtering here -- the RLS SELECT policy on
        organization_candidate_assignments already scopes this
        correctly per caller (owners/admins see every assignment in
        the org, a manager/staff sees only their own caseload), same
        pattern as list_members and list_invites.
        """
        rows = self.db.select(
            self.ASSIGNMENT_TABLE,
            params={"select": "*", "organization_id": f"eq.{organization_id}", "order": "created_at.desc"},
        )
        return [CandidateAssignment.model_validate(r) for r in rows]

    def delete_assignment(self, organization_id: UUID, assignment_id: UUID) -> bool:
        rows = self.db.delete(
            self.ASSIGNMENT_TABLE,
            params={"id": f"eq.{assignment_id}", "organization_id": f"eq.{organization_id}"},
        )
        return bool(rows)

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def list_members(self, organization_id: UUID) -> list[OrganizationMember]:
        """Uses list_organization_members_with_email() (migration 0012)
        rather than a plain select against organization_members --
        that table has no email column, and PostgREST can't reach the
        auth schema for a join. The function itself re-checks
        is_org_member() and simply returns no rows for a non-member,
        same fail-closed behavior as the RLS SELECT policy it extends
        (verified directly against production, not assumed).
        """
        rows = self.db.rpc(
            "list_organization_members_with_email", {"p_organization_id": str(organization_id)}
        )
        return [OrganizationMember.model_validate(r) for r in rows]

    def get_member_role(self, organization_id: UUID, member_id: UUID) -> str | None:
        """Internal-only lookup (no email) -- used by the router's own
        orphan/privilege guards before a remove or role-change, not
        exposed as an API response shape.
        """
        rows = self.db.select(
            self.MEMBER_TABLE,
            params={"select": "role", "id": f"eq.{member_id}", "organization_id": f"eq.{organization_id}"},
        )
        if not rows:
            return None
        return rows[0]["role"]

    def count_owners(self, organization_id: UUID) -> int:
        """Used to block removing/demoting the org's last owner -- RLS
        (is_org_admin, migration 0007) permits owners and admins alike
        to delete/update organization_members rows, but has no concept
        of 'don't orphan the org' built in. That guard lives here, at
        the app layer, checked before every remove/role-change call.
        """
        rows = self.db.select(
            self.MEMBER_TABLE,
            params={"select": "id", "organization_id": f"eq.{organization_id}", "role": "eq.owner"},
        )
        return len(rows)

    def remove_member(self, organization_id: UUID, member_id: UUID) -> bool:
        """Caller is responsible for the orphan/privilege checks (see
        organizations.py router's remove_member endpoint) -- this is
        the mechanical delete only, relying on RLS (is_org_admin) as
        the actual authorization boundary, same as revoke_invite.
        """
        rows = self.db.delete(
            self.MEMBER_TABLE,
            params={"id": f"eq.{member_id}", "organization_id": f"eq.{organization_id}"},
        )
        return bool(rows)

    def update_member_role(
        self, organization_id: UUID, member_id: UUID, new_role: str
    ) -> OrganizationMember | None:
        """Same split as remove_member -- guards live in the router,
        this is the mechanical update. Re-fetches with email afterward
        (list_organization_members_with_email doesn't take a single-
        member filter, so this does one extra round trip rather than
        adding a second RPC variant for a single row)."""
        rows = self.db.update(
            self.MEMBER_TABLE,
            data={"role": new_role},
            params={"id": f"eq.{member_id}", "organization_id": f"eq.{organization_id}"},
        )
        if not rows:
            return None
        members = self.list_members(organization_id)
        return next((m for m in members if str(m.id) == str(member_id)), None)

    # ------------------------------------------------------------------
    # Invites -- admin-facing (normal RLS via is_org_admin)
    # ------------------------------------------------------------------

    def create_invite(
        self, organization_id: UUID, email: str, role: str, invited_by: UUID
    ) -> OrganizationInviteCreated:
        payload = {
            "organization_id": str(organization_id),
            "email": email.strip().lower(),
            "role": role,
            "invited_by": str(invited_by),
        }
        rows = self.db.insert(self.INVITE_TABLE, payload)
        return OrganizationInviteCreated.model_validate(rows[0])

    def list_invites(self, organization_id: UUID) -> list[OrganizationInvite]:
        rows = self.db.select(
            self.INVITE_TABLE,
            params={
                "select": "id,organization_id,email,role,status,invited_by,created_at,expires_at,accepted_at",
                "organization_id": f"eq.{organization_id}",
                "order": "created_at.desc",
            },
        )
        return [OrganizationInvite.model_validate(r) for r in rows]

    def revoke_invite(self, invite_id: UUID, organization_id: UUID) -> OrganizationInvite | None:
        """Scoped by both invite_id and organization_id -- belt-and-braces
        against a stale/cross-org id, on top of the RLS is_org_admin()
        check which already prevents cross-org revocation.
        """
        rows = self.db.update(
            self.INVITE_TABLE,
            data={"status": "revoked"},
            params={"id": f"eq.{invite_id}", "organization_id": f"eq.{organization_id}"},
        )
        if not rows:
            return None
        return OrganizationInvite.model_validate(rows[0])

    # ------------------------------------------------------------------
    # Invites -- invitee-facing (crosses the membership boundary)
    # ------------------------------------------------------------------

    @staticmethod
    def get_invite_preview(token: str) -> InvitePreview | None:
        """Anon-key client, deliberately -- this must work before login.
        Static because it never touches self.db: the whole point is
        that this works for someone who isn't authenticated at all.
        """
        anon_db = SupabaseClient(access_token=settings.supabase_anon_key)
        rows = anon_db.rpc("get_invite_preview", {"p_token": token})
        if not rows:
            return None
        return InvitePreview.model_validate(rows[0])

    def accept_invite(self, token: str) -> UUID:
        """Atomic: validates the invite (pending, not expired, email
        matches the caller's verified JWT email) and inserts membership
        in one transaction, via accept_organization_invite(). Called
        with the invitee's own user-scoped client -- see module
        docstring for why this is never service_role.

        Returns the organization_id the caller just joined. Raises
        SupabaseError with the function's own message (invite not
        found, expired, wrong email, already in an org) -- the router
        maps this to a 400 rather than letting main.py's generic 502
        handler swallow the real reason.
        """
        organization_id = self.db.rpc("accept_organization_invite", {"p_token": token})
        return UUID(organization_id)
