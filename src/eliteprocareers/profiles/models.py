"""
Domain models for the candidate profile — the canonical, typed representation
used throughout the application. Independent of the database and any UI.

Raw dicts from Supabase/PostgREST should never cross into service or
application logic — profiles/repository.py is the only place that maps
between these models and the database.
"""

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class ProficiencyLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class LanguageProficiency(str, Enum):
    basic = "basic"
    conversational = "conversational"
    fluent = "fluent"
    native = "native"


class CandidateProfile(BaseModel):
    id: UUID | None = None
    user_id: UUID
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Skill(BaseModel):
    id: UUID | None = None
    name: str
    created_at: datetime | None = None


class CandidateSkill(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    skill_id: UUID
    proficiency_level: ProficiencyLevel | None = None
    years_experience: float | None = None
    created_at: datetime | None = None
    # Convenience field, populated by the repository on read (not a DB column)
    skill_name: str | None = None


class WorkExperience(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    company: str
    title: str
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Education(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None
    created_at: datetime | None = None


class Certification(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    name: str
    issuer: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    created_at: datetime | None = None


class Language(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    language: str
    proficiency: LanguageProficiency | None = None
    created_at: datetime | None = None


class Project(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    name: str
    description: str | None = None
    url: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime | None = None


class Achievement(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    work_experience_id: UUID | None = None
    description: str
    achieved_date: date | None = None
    created_at: datetime | None = None


class Reference(BaseModel):
    id: UUID | None = None
    profile_id: UUID
    name: str
    relationship: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    created_at: datetime | None = None


class FullProfile(BaseModel):
    """Composite view: a candidate_profiles row plus every related table,
    assembled by ProfileRepository.get_full_profile(). Not a database table.
    """
    profile: CandidateProfile
    skills: list[CandidateSkill] = []
    work_experience: list[WorkExperience] = []
    education: list[Education] = []
    certifications: list[Certification] = []
    languages: list[Language] = []
    projects: list[Project] = []
    achievements: list[Achievement] = []
    references: list[Reference] = []
