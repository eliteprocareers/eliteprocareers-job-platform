"""
Domain model for user_job_matches — a scored match between a user's CV
track and a real ingested job. Maps directly to the user_job_matches
table. Rows are created by the scoring engine (scoring/embeddings.py)
running compute_match_score() against a real Job + CVTrack pair.

RLS note: unlike jobs (backend-owned, service_role writes), this table
is per-user with a user-scoped RLS policy (user_id = auth.uid()) -- the
repository must be constructed with a normal user-scoped SupabaseClient,
not use_service_role=True. Confirmed against migrations/0001_init_schema.sql
and 0002_optimize_rls_and_indexes.sql before writing this model.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserJobMatch(BaseModel):
    """Maps directly to the user_job_matches table.

    unique (user_id, job_id, cv_track_id) in the DB -- a given track can
    only have one match row per job. Re-scoring should update the
    existing row, not insert a duplicate (see repository.py's
    upsert_match()).
    """
    id: UUID | None = None
    user_id: UUID
    job_id: UUID
    cv_track_id: UUID
    match_score: float | None = None
    ai_rationale: str | None = None
    scored_at: datetime | None = None
