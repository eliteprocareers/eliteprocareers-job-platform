"""
Job domain model — mirrors the `jobs` table exactly (migrations/0001_init_schema.sql).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Job(BaseModel):
    id: UUID
    source: str  # 'greenhouse' | 'lever' | 'workday'
    external_id: str
    company: str
    title: str
    description: str | None = None
    url: str | None = None
    location: str | None = None
    posted_at: datetime | None = None
    ingested_at: datetime
    raw_json: dict | None = None

    # Normalized, connector-populated attributes (migration 0003).
    # Known key set: employment_type, seniority_level, industry,
    # work_mode, country, visa_sponsorship, salary_min, salary_max,
    # salary_currency. Connectors populate whatever subset they can
    # actually extract -- absent keys mean "unknown", not "no". The
    # filtering engine must check key presence before applying any
    # rule against this dict.
    attributes: dict = Field(default_factory=dict)
