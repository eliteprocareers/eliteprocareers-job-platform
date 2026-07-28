"""
API-only schemas -- request/response shapes that don't already exist as
domain models under profiles/, jobs/, matching/. Those domain models are
reused directly as response_model wherever they already fit; this file is
only for shapes specific to the HTTP layer itself.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from eliteprocareers.organizations.models import InvitableRole, MemberRole, OrgType, SharingMode
from eliteprocareers.profiles.models import ApplicationStatus, GeneratedDocument


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str | None = None


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class SignupResponse(BaseModel):
    """access_token/refresh_token are None if the Supabase project has
    email confirmation enabled -- the account exists but isn't usable
    until the person clicks the confirmation link, then logs in
    separately via POST /auth/login. requires_confirmation tells the
    frontend which case it's in without it having to guess from
    null-ness alone.
    """
    user_id: str
    email: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    requires_confirmation: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"


class MatchWithJob(BaseModel):
    """A user_job_matches row joined with the job it points to, since
    UserJobMatch alone only carries job_id -- callers displaying a match
    list need the title/company/url too. Assembled in the matches router,
    not a real view/table.
    """
    match_id: UUID
    job_id: UUID
    match_score: float | None
    ai_rationale: str | None
    scored_at: datetime | None
    job_title: str
    job_company: str
    job_url: str | None
    job_location: str | None


class CreateTrackRequest(BaseModel):
    """Body for POST /tracks. user_id is deliberately absent -- it's
    always taken from the authenticated token, never the request body.
    """
    track_name: str
    target_roles: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_countries: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    seniority_levels: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    willing_to_relocate: bool = False
    visa_sponsorship_required: bool | None = None
    work_authorization_status: str | None = None
    salary_expectation_min: float | None = None
    salary_expectation_max: float | None = None
    salary_currency: str | None = None
    auto_apply_enabled: bool = False
    auto_apply_min_score: float = 0.85
    undo_window_minutes: int | None = 15


class UpdateTrackRequest(BaseModel):
    """Body for PUT /tracks/{track_id}. Every field is optional and has
    no default -- the router uses model_dump(exclude_unset=True) so an
    omitted field is left untouched in the DB, not overwritten with []
    or None.
    """
    track_name: str | None = None
    target_roles: list[str] | None = None
    scoring_weights: dict[str, float] | None = None
    preferred_locations: list[str] | None = None
    preferred_countries: list[str] | None = None
    employment_types: list[str] | None = None
    seniority_levels: list[str] | None = None
    industries: list[str] | None = None
    work_mode: list[str] | None = None
    willing_to_relocate: bool | None = None
    visa_sponsorship_required: bool | None = None
    work_authorization_status: str | None = None
    salary_expectation_min: float | None = None
    salary_expectation_max: float | None = None
    salary_currency: str | None = None
    auto_apply_enabled: bool | None = None
    auto_apply_min_score: float | None = None
    undo_window_minutes: int | None = None


class CVUploadTriggerResponse(BaseModel):
    """Response for POST /profile/cv-upload. Parsing happens in the
    background (BackgroundTasks), same reason as MatchTriggerResponse
    below -- LLM extraction takes a few seconds, long enough that doing
    it inline would make the upload request itself feel hung. Poll
    GET /profile/cv-upload-status/{upload_id} for real completion
    status.
    """
    upload_id: UUID
    filename: str
    status: str = "processing"
    message: str


class MatchTriggerResponse(BaseModel):
    """Response for POST /tracks/{track_id}/match. The actual matching
    run happens in the background (BackgroundTasks) -- this just
    acknowledges it started. run_id can be polled via
    GET /tracks/{track_id}/match-status/{run_id} for real completion
    status (see matching/models.py's MatchingRun), replacing the
    earlier client-side timed-poll workaround against
    GET /tracks/{track_id}/matches.
    """
    track_id: UUID
    track_name: str
    run_id: UUID
    status: str = "started"
    message: str


class ScreeningAnswerRequest(BaseModel):
    """Body for POST /tracks/{track_id}/jobs/{job_id}/generate-screening-answer."""
    question: str
    word_limit: int | None = None


class DocumentsBundle(BaseModel):
    """Response for GET /tracks/{track_id}/jobs/{job_id}/documents -- the
    latest version of each doc type for this track+job, or None if that
    type hasn't been generated yet.
    """
    cv: GeneratedDocument | None = None
    cover_letter: GeneratedDocument | None = None
    screening_answer: GeneratedDocument | None = None


class CreateApplicationRequest(BaseModel):
    """Body for POST /tracks/{track_id}/jobs/{job_id}/applications. Optional
    free-text notes only -- status always starts at 'draft', job_id/
    cv_track_id/user_id all come from the path and the authenticated
    token, never the body, same rule as every other create-request in
    this API.
    """
    notes: str | None = None


class UpdateApplicationStatusRequest(BaseModel):
    """Body for PATCH /tracks/{track_id}/applications/{application_id}.
    status is validated against ApplicationStatus here so a bad value
    422s before ever reaching PostgREST's own check constraint.
    """
    status: ApplicationStatus
    notes: str | None = None


class CreateOrganizationRequest(BaseModel):
    """Body for POST /organizations. Rejected server-side (RPC-level,
    not just here) if the caller already belongs to an org -- see
    create_organization_with_owner() in migration 0010.
    """
    name: str
    org_type: OrgType = OrgType.individual


class CreateInviteRequest(BaseModel):
    """Body for POST /organizations/invites. Admin/owner only, enforced
    by RLS (is_org_admin), not just the endpoint's own auth check.
    """
    email: EmailStr
    role: InvitableRole = InvitableRole.staff


class AcceptInviteRequest(BaseModel):
    """Body for POST /organizations/invites/accept."""
    token: str


class UpdateOrganizationRequest(BaseModel):
    """Body for PATCH /organizations. All fields optional -- a partial
    update. Admin/owner only, enforced by RLS (is_org_admin), same as
    every other admin-gated org write. sharing_mode (migration 0015)
    is the org-wide opt-in to full sharing instead of assigned_only.
    """
    name: str | None = None
    org_type: OrgType | None = None
    sharing_mode: SharingMode | None = None


class CreateAssignmentRequest(BaseModel):
    """Body for POST /organizations/assignments. manage_assignments
    (owner/admin only) -- see organizations/permissions.py.
    """
    candidate_user_id: UUID
    assigned_to: UUID


class UpdateMemberRoleRequest(BaseModel):
    """Body for PATCH /organizations/members/{member_id}/role. Accepts
    the full MemberRole set (including 'owner') -- unlike invites,
    which can only ever grant admin/member -- but granting or removing
    'owner' is gated at the router level to owners-only, and the last
    owner can never be demoted. See organizations.py.
    """
    role: MemberRole


class ApplicationWithJob(BaseModel):
    """An applications row joined with the job it points to -- same
    reasoning as MatchWithJob: Application alone only carries job_id,
    callers displaying an applications list need title/company/url too.
    """
    id: UUID
    job_id: UUID
    cv_track_id: UUID
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None
    created_at: datetime | None
    job_title: str
    job_company: str
    job_url: str | None
    auto_applied: bool = False
    queued_at: datetime | None = None
    undo_deadline: datetime | None = None
    failure_reason: str | None = None
