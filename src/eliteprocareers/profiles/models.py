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

from pydantic import BaseModel, Field 


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
class CVTrack(BaseModel):
    """A named CV strategy track (e.g. 'Product Management' vs 'Supply Chain').

    Pure configuration — target roles and scoring weights. Generated CVs,
    cover letters, and match scores live elsewhere and reference this by id.
    """
    id: UUID | None = None
    user_id: UUID
    track_name: str
    target_roles: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, float] = Field(default_factory=dict)

    # Structured filter preferences (migration 0003). Each field drives
    # a specific Stage-1 filter -- see matching/filtering.py. Empty
    # list / None means "no preference", not "excludes everything" --
    # the filtering engine must treat unset preferences as non-restrictive.
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

    created_at: datetime | None = None
    updated_at: datetime | None = None
class DocType(str, Enum):
    cv = "cv"
    cover_letter = "cover_letter"
    screening_answer = "screening_answer"


class GeneratedDocument(BaseModel):
    """Maps directly to the generated_documents table.

    content is always a plain string in the DB. For doc_type='cv', that
    string is JSON produced by CVContent.to_json() — parse it back with
    CVContent.from_json(doc.content). For cover_letter/screening_answer,
    content is just the plain generated text.
    """
    id: UUID | None = None
    user_id: UUID
    cv_track_id: UUID
    application_id: UUID | None = None
    doc_type: DocType
    content: str
    version: int = 1
    ai_model_used: str | None = None
    created_at: datetime | None = None


class CVWorkExperienceEntry(BaseModel):
    title: str
    company: str
    dates: str
    bullets: list[str] = Field(default_factory=list)


class CVContent(BaseModel):
    """Structured representation of a tailored CV, before it's serialized
    into GeneratedDocument.content as JSON. Kept separate from
    GeneratedDocument because the DB column is just text — this model
    defines what that text means when doc_type='cv'.
    """
    summary: str
    skills: list[str] = Field(default_factory=list)
    work_experience: list[CVWorkExperienceEntry] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "CVContent":
        return cls.model_validate_json(raw)
