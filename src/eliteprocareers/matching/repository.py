"""
UserJobMatchRepository -- per-user scored matches between CV tracks and
real ingested jobs.

RLS note: user_job_matches is scoped by can_view_org_resource(
organization_id, user_id) as of migration 0015 (previously
user_id = auth.uid() only), unlike jobs (backend-owned, service_role).
This repository must be constructed with a normal user-scoped
SupabaseClient (access_token path), not use_service_role=True.

organization_id note (migration 0007, bug found and fixed 2026-07-29):
user_job_matches.organization_id has been NOT NULL, no default, since
migration 0007 -- but upsert_match()'s INSERT payload never set it,
because the column post-dated the method and nothing forced a look at
it again. This went unnoticed because every real matching run between
0007 (2026-07-26) and this fix only ever hit the UPDATE branch (existing
tracks re-scoring already-matched jobs, which doesn't touch
organization_id) -- confirmed by checking matching_runs' history
directly: no INSERT into user_job_matches had been attempted since the
column went NOT NULL. Any brand-new track's first matching run, or any
newly-ingested job, would have hard-failed on the very first job that
cleared Stage 1, aborting the whole run silently (caught by
run_matching_for_track_tracked's except-clause, surfaced only as a
generic matching_runs.status='failed' row with no indication of the
real cause). Fixed by requiring organization_id on upsert_match() and
sourcing it from the track's own organization_id in matching_service.py,
never from a caller-supplied value.

No native upsert support exists in SupabaseClient yet (confirmed --
no resolution=merge-duplicates/on_conflict support in db/client.py),
so upsert_match() does select-then-insert-or-update rather than
relying on a PostgREST feature that isn't wired up.
"""
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from datetime import datetime, timezone

from eliteprocareers.matching.models import MatchingRun, UserJobMatch


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
        organization_id: UUID,
        ai_rationale: str | None = None,
    ) -> UserJobMatch:
        """Create a new match row, or update the existing one if this
        (user, job, track) triple was already scored -- re-scoring
        should overwrite, not duplicate (DB has a unique constraint on
        this triple that would otherwise reject a second insert).

        organization_id is required and only ever used on the INSERT
        path -- it can't legitimately change for an existing match (a
        track doesn't move between orgs), so the UPDATE payload
        deliberately never touches it, same reasoning as ai_rationale's
        own update guard below. Caller must pass the match's owning
        track's own organization_id (matching_service.py sources this
        from track.organization_id, never from whichever caller
        triggered the run) -- see this module's docstring for why this
        parameter exists at all (migration 0007 bug, fixed 2026-07-29).

        On update, ai_rationale is only written when the caller passes
        one explicitly. Without this guard, re-running matching_service's
        run_matching_for_track() (which never passes ai_rationale) would
        silently null out every rationale backfill_match_rationales.py
        had written -- caught live 2026-07-20 before it happened, while
        about to re-score the Product Management/SaaS track after
        widening its target_roles, right after finishing a full
        rationale backfill for that same track.
        """
        existing = self.get_match(user_id, job_id, cv_track_id)

        if existing is not None:
            payload: dict = {"match_score": match_score}
            if ai_rationale is not None:
                payload["ai_rationale"] = ai_rationale
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
            "match_score": match_score,
            "ai_rationale": ai_rationale,
            "organization_id": str(organization_id),
        }
        rows = self.db.insert(self.TABLE, payload)
        return UserJobMatch.model_validate(rows[0])

    def update_rationale(self, match_id: UUID, ai_rationale: str) -> UserJobMatch:
        """Writes ai_rationale for an existing match row without touching
        match_score. Deliberately separate from upsert_match(), which
        requires (and would overwrite) match_score -- a rationale-only
        backfill pass has no new score to give it and shouldn't risk
        clobbering a real one with a stale re-read.
        """
        rows = self.db.update(
            self.TABLE,
            {"ai_rationale": ai_rationale},
            params={"id": f"eq.{match_id}"},
        )
        return UserJobMatch.model_validate(rows[0])

    def delete_match(self, match_id: UUID) -> None:
        """Deletes one match row by id. Used by cleanup scripts to remove
        stale matches -- e.g. a row scored before Stage-1 filtering
        existed, for a job that would now FAIL Stage 1.
        """
        self.db.delete(self.TABLE, params={"id": f"eq.{match_id}"})

    def list_matches_for_track(
        self, cv_track_id: UUID, min_score: float | None = None
    ) -> list[UserJobMatch]:
        """All matches for a given CV track, best-first. min_score filters
        out low-quality matches (e.g. 0.3) so callers don't have to sort
        through noise -- optional since some callers may want everything.

        Paginated -- PostgREST caps unpaginated GET responses at 1000 rows
        by default. Confirmed live 2026-07-20: both of James's tracks
        returned exactly 1000 rows each before this fix, silently
        truncating cleanup_stale_matches.py's dry run. Same cap, same
        fix pattern as JobRepository.get_existing_external_ids()/list_all().
        """
        page_size = 1000
        offset = 0
        all_matches: list[UserJobMatch] = []

        while True:
            params = {
                "select": "*",
                "cv_track_id": f"eq.{cv_track_id}",
                "order": "match_score.desc",
                "limit": page_size,
                "offset": offset,
            }
            if min_score is not None:
                params["match_score"] = f"gte.{min_score}"

            rows = self.db.select(self.TABLE, params=params)
            all_matches.extend(UserJobMatch.model_validate(r) for r in rows)
            if len(rows) < page_size:
                break
            offset += page_size

        return all_matches


class MatchingRunRepository:
    """Tracks status of background matching runs (matching_runs table),
    for real status-polling via GET /tracks/{id}/match-status/{run_id}.

    RLS: can_view_org_resource(organization_id, user_id) as of migration
    0016 (previously user_id = auth.uid() only, from migration
    0004_add_matching_runs.sql) -- must be constructed with a
    user-scoped SupabaseClient, not use_service_role=True, same rule as
    UserJobMatchRepository.
    """
    TABLE = "matching_runs"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def create_run(self, user_id: UUID, cv_track_id: UUID, organization_id: UUID) -> MatchingRun:
        """Called at the start of a matching run, before any jobs are
        processed -- gives the caller a run_id to return to the client
        immediately, before jobs_total is even known.

        organization_id is required (migration 0016, matching_runs'
        organization_id column is NOT NULL) -- caller must pass the
        run's owning track's own organization_id (track.user_id's org),
        not necessarily the triggering caller's, same sourcing rule as
        matching_service.py's run_matching_for_track.
        """
        payload = {
            "user_id": str(user_id),
            "cv_track_id": str(cv_track_id),
            "organization_id": str(organization_id),
            "status": "running",
            "jobs_processed": 0,
        }
        rows = self.db.insert(self.TABLE, payload)
        return MatchingRun.model_validate(rows[0])

    def update_progress(
        self, run_id: UUID, jobs_processed: int, jobs_total: int
    ) -> None:
        """Called from on_progress during the run. Caller is responsible
        for throttling call frequency -- this does one write per call,
        with no batching of its own.
        """
        self.db.update(
            self.TABLE,
            {"jobs_processed": jobs_processed, "jobs_total": jobs_total},
            params={"id": f"eq.{run_id}"},
        )

    def mark_completed(self, run_id: UUID) -> None:
        self.db.update(
            self.TABLE,
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            params={"id": f"eq.{run_id}"},
        )

    def mark_failed(self, run_id: UUID, error_message: str) -> None:
        """Called if run_matching_for_track raises. error_message is
        str(exc) -- not the full traceback, to avoid leaking internal
        details to a client polling this row.
        """
        self.db.update(
            self.TABLE,
            {
                "status": "failed",
                "error_message": error_message,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            params={"id": f"eq.{run_id}"},
        )

    def get_run(self, run_id: UUID) -> MatchingRun | None:
        rows = self.db.select(
            self.TABLE, params={"select": "*", "id": f"eq.{run_id}"}
        )
        if not rows:
            return None
        return MatchingRun.model_validate(rows[0])

    # A "running" row older than this is treated as dead, not in-flight.
    # Added 2026-08-06 after finding 10 matching_runs rows stuck at
    # 'running' in production, some over a week old -- confirmed via
    # Vercel:get_runtime_errors as "Application exited with code 143
    # (SIGTERM)" (function-duration kills mid-run), most recently
    # 2026-08-05. A SIGTERM'd process never reaches run_matching_for_
    # track_tracked's except block, so mark_failed() is never called --
    # the row is orphaned permanently and get_running_run_for_track's
    # 409-conflict check then blocks every future retry forever, with
    # no way to recover short of manual SQL. STALE_RUN_SECONDS is set
    # well above the function's maxDuration (300s as of v42, see
    # vercel.json -- 800s was rejected by the actual plan; see v42
    # handover and docs/resumable-matching-design.md) so a genuinely
    # still-running call is never reaped out from under itself.
    STALE_RUN_SECONDS = 1200

    def get_running_run_for_track(self, cv_track_id):
        """Any matching_runs row still in-flight (status='running') for
        this track. Used by trigger_matching to refuse starting a second
        overlapping run -- two concurrent runs on the same track raced
        auto-apply's idempotency check for the same job in production on
        2026-07-27, producing duplicate applications until
        uq_applications_track_job (migration 0010) caught it at the DB
        level. This closes the root cause the constraint only patches
        around.

        If the most recent 'running' row is older than STALE_RUN_SECONDS,
        it's reaped here: marked 'failed' with an explanatory message and
        treated as not-running (returns None), so the caller can start a
        fresh run instead of being blocked by a run that Vercel's
        platform already silently killed. See STALE_RUN_SECONDS docstring
        for why this is safe against a genuinely in-flight run.
        """
        rows = self.db.select(
            self.TABLE,
            params={
                "select": "*",
                "cv_track_id": f"eq.{cv_track_id}",
                "status": "eq.running",
                "order": "started_at.desc",
                "limit": "1",
            },
        )
        if not rows:
            return None
        run = MatchingRun.model_validate(rows[0])

        # started_at is `not null default now()` in the schema (migration
        # 0004) so this should always be set for a real row -- None is
        # only reachable if a row were ever inserted bypassing the DB
        # default entirely, which nothing in this codebase does. Treat
        # that as not-stale rather than crash on the subtraction below.
        if run.started_at is None:
            return run

        age_seconds = (
            datetime.now(timezone.utc) - run.started_at
        ).total_seconds()
        if age_seconds > self.STALE_RUN_SECONDS:
            self.mark_failed(
                run.id,
                (
                    f"Auto-reaped as stale after {int(age_seconds)}s with no "
                    f"completion (last progress: {run.jobs_processed}/"
                    f"{run.jobs_total} jobs) -- almost certainly a Vercel "
                    "function-duration kill (SIGTERM) mid-run, not a real "
                    "in-progress run."
                ),
            )
            return None
        return run
