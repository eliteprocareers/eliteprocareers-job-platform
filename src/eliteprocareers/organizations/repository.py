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

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def list_members(self, organization_id: UUID) -> list[OrganizationMember]:
        rows = self.db.select(
            self.MEMBER_TABLE,
            params={"select": "*", "organization_id": f"eq.{organization_id}"},
        )
        return [OrganizationMember.model_validate(r) for r in rows]

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
