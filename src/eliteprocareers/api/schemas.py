"""
API-only schemas -- request/response shapes that don't already exist as
domain models under profiles/, jobs/, matching/. Those domain models are
reused directly as response_model wherever they already fit; this file is
only for shapes specific to the HTTP layer itself.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from eliteprocareers.profiles.models import GeneratedDocument


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str | None = None


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
