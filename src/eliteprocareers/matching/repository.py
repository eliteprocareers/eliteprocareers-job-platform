"""
UserJobMatchRepository -- per-user scored matches between CV tracks and
real ingested jobs.

RLS note: user_job_matches has a user-scoped RLS policy
(user_id = auth.uid()), unlike jobs (backend-owned, service_role).
This repository must be constructed with a normal user-scoped
SupabaseClient (access_token path), not use_service_role=True.
Confirmed against migrations/0001_init_schema.sql before writing this.

No native upsert support exists in SupabaseClient yet (confirmed --
no resolution=merge-duplicates/on_conflict support in db/client.py),
so upsert_match() does select-then-insert-or-update rather than
relying on a PostgREST feature that isn't wired up.
"""
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.matching.models import UserJobMatch


class UserJobMatchRepository:
    TABLE = "user_job_matches"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def get_match(
        self, user_id: UUID, job_id: UUID, cv_track_id: UUID
    ) -> UserJobMatch | None:
        """Fetch the existing match row for this exact (user, job, track)
        triple, if one exists. Relies on the DB's unique constraint --
        at most one row can ever match these filters.
        """
        rows = self.db.select(
            self.TABLE,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "job_id": f"eq.{job_id}",
                "cv_track_id": f"eq.{cv_track_id}",
            },
        )
        if not rows:
            return None
        return UserJobMatch.model_validate(rows[0])

    def upsert_match(
        self,
        user_id: UUID,
        job_id: UUID,
        cv_track_id: UUID,
        match_score: float,
        ai_rationale: str | None = None,
    ) -> UserJobMatch:
        """Create a new match row, or update the existing one if this
        (user, job, track) triple was already scored -- re-scoring
        should overwrite, not duplicate (DB has a unique constraint on
        this triple that would otherwise reject a second insert).
        """
        existing = self.get_match(user_id, job_id, cv_track_id)

        payload = {
            "match_score": match_score,
            "ai_rationale": ai_rationale,
        }

        if existing is not None:
            rows = self.db.update(
                self.TABLE,
                payload,
                params={"id": f"eq.{existing.id}"},
            )
            return UserJobMatch.model_validate(rows[0])

        payload = {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "cv_track_id": str(cv_track_id),
            **payload,
        }
        rows = self.db.insert(self.TABLE, payload)
        return UserJobMatch.model_validate(rows[0])

    def list_matches_for_track(
        self, cv_track_id: UUID, min_score: float | None = None
    ) -> list[UserJobMatch]:
        """All matches for a given CV track, best-first. min_score filters
        out low-quality matches (e.g. 0.3) so callers don't have to sort
        through noise -- optional since some callers may want everything.
        """
        params = {
            "select": "*",
            "cv_track_id": f"eq.{cv_track_id}",
            "order": "match_score.desc",
        }
        if min_score is not None:
            params["match_score"] = f"gte.{min_score}"

        rows = self.db.select(self.TABLE, params=params)
        return [UserJobMatch.model_validate(r) for r in rows]
