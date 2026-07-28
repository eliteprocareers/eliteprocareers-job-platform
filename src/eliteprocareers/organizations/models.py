"""
Domain models for the multi-tenant organizations layer -- organizations,
membership, and invites. Mirrors profiles/models.py's convention: raw
PostgREST dicts are translated to/from these models in
organizations/repository.py and nowhere else.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr


class OrgType(str, Enum):
    individual = "individual"
    agency = "agency"
    staffing_firm = "staffing_firm"
    company = "company"
    university = "university"
    career_coaching_firm = "career_coaching_firm"
    enterprise = "enterprise"


class MemberRole(str, Enum):
    owner = "owner"
    admin = "admin"
    manager = "manager"
    staff = "staff"


class InvitableRole(str, Enum):
    """Roles that can be granted via invite. Deliberately excludes
    'owner' -- ownership isn't transferable through the invite flow.
    """

    admin = "admin"
    manager = "manager"
    staff = "staff"


class InviteStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class Organization(BaseModel):
    id: UUID
    name: str
    org_type: OrgType
    created_at: datetime
    updated_at: datetime


class OrganizationMember(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: MemberRole
    created_at: datetime
    # Backed by list_organization_members_with_email() (migration
    # 0012) -- organization_members itself has no email column, and
    # PostgREST can't reach the auth schema for a client-side join.
    # Any org member can see this for fellow members, matching the
    # existing membership-visibility RLS policy this extends.
    email: str


class OrganizationInvite(BaseModel):
    """The admin-facing view of an invite. Deliberately excludes
    `token` -- the link is only ever shown once, at creation time
    (see OrganizationInviteCreated), never in a subsequent list call.
    """

    id: UUID
    organization_id: UUID
    email: EmailStr
    role: InvitableRole
    status: InviteStatus
    invited_by: UUID
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None


class OrganizationInviteCreated(OrganizationInvite):
    """Returned only from the create-invite endpoint -- the one moment
    the token is exposed, so the admin can copy/share the invite link.
    There is no email-sending integration yet (flagged as a gap in the
    handover); the admin must share this link manually.
    """

    token: str


class InvitePreview(BaseModel):
    """Unauthenticated-safe preview of an invite by token, for a
    "you've been invited to X" landing page before the person has
    logged in. Backed by get_invite_preview(), which deliberately
    exposes nothing beyond this.
    """

    organization_name: str
    email: EmailStr
    role: InvitableRole
    status: InviteStatus
    expires_at: datetime
