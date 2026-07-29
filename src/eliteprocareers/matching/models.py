"""
Domain model for user_job_matches — a scored match between a user's CV
track and a real ingested job. Maps directly to the user_job_matches
table. Rows are created by the scoring engine (scoring/embeddings.py)
running compute_match_score() against a real Job + CVTrack pair.

RLS note: unlike jobs (backend-owned, service_role writes), this table
is scoped by can_view_org_resource(organization_id, user_id) as of
migration 0015 (previously user_id = auth.uid() only, from
migrations/0001_init_schema.sql and 0002_optimize_rls_and_indexes.sql)
-- own rows, org owner/admin, full-sharing org member, or assigned
staff. The repository must still be constructed with a normal
user-scoped SupabaseClient, not use_service_role=True, for the same
reason as before: service_role bypasses RLS entirely, which is wrong
for a write that must be scoped to the caller's real visibility.
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


class MatchingRun(BaseModel):
    """Maps directly to the matching_runs table -- one row per triggered
    matching run (POST /tracks/{id}/match), updated as it progresses.
    Lets a client poll GET .../match-status/{run_id} for real completion
    status, replacing the client-side timed-poll workaround. See
    migrations/0004_add_matching_runs.sql.
    """
    id: UUID | None = None
    user_id: UUID
    cv_track_id: UUID
    # organization_id (migration 0016): required now that matching_runs'
    # RLS is can_view_org_resource()-based instead of user_id = auth.uid()
    # only -- see migration 0016's comment for why the run-log needed
    # the same assignment-aware visibility as the five candidate-data
    # tables.
    organization_id: UUID
    status: str = "running"  # running | completed | failed
    jobs_total: int | None = None
    jobs_processed: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
