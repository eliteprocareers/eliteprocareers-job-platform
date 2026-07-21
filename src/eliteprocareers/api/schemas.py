"""
API-only schemas -- request/response shapes that don't already exist as
domain models under profiles/, jobs/, matching/. Those domain models are
reused directly as response_model wherever they already fit; this file is
only for shapes specific to the HTTP layer itself.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


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
