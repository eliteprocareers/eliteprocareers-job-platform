"""
Job domain model — mirrors the `jobs` table exactly (migrations/0001_init_schema.sql).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
