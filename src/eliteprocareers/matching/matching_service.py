"""
Matching service -- runs Stage-1 filtering and Stage-2 embedding-based
scoring for one CV track against every job currently in the `jobs`
table, and upserts a user_job_matches row for every job that passes
Stage 1.

Pure application logic: no printing, no argv. Callable from
scripts/run_matching.py, tests, or a future API endpoint.

Uses the service_role key for reading jobs/profile/track data (backend
operation, same trust level as ingestion). Writing matches via
UserJobMatchRepository here also goes through service_role, which
bypasses that table's can_view_org_resource() RLS policy -- acceptable
for this backend-run script since it's explicitly scoped to one
user_id at a time, but a future per-user API endpoint calling this
must NOT reuse service_role for the match-write step; it should
construct a user-scoped SupabaseClient instead, per
matching/repository.py's docstring.

organization_id sourcing (fixed 2026-07-29, see matching/repository.py's
docstring for the bug this replaced): run_matching_for_track no longer
accepts organization_id as a parameter. It reads track.organization_id
-- the CV track's own, authoritative org -- and uses that for both the
match upsert and maybe_auto_apply(), instead of trusting whichever
caller happened to trigger the run. This fixes two real problems at
once: (1) the user_job_matches INSERT bug (organization_id was never
being set at all), and (2) the assignment-awareness gap trigger_matching's
docstring flagged 2026-07-28 -- an assigned staff member triggering a
run on a candidate's track now correctly scopes every write to the
candidate's own org, not the staff member's caller-supplied one (today
these are always the same org, since multi-org-per-user is still
hard-blocked at one -- but sourcing from the track is correct
regardless of whether that constraint ever lifts, and doesn't rely on
every future caller remembering to pass the right value).
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.auto_apply import maybe_auto_apply
from eliteprocareers.matching.filtering import (
    CriterionResult,
    passes_stage1,
    run_stage1_filters,
)
from eliteprocareers.matching.repository import (
    MatchingRunRepository,
    UserJobMatchRepository,
)
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository
from eliteprocareers.scoring.embeddings import (
    build_job_text,
    compute_industry_mismatch_penalty,
    compute_match_score,
)


@dataclass
class MatchOutcome:
    job_id: UUID
    job_title: str
    stage1_passed: bool
    stage1_results: list[CriterionResult]
    match_score: float | None = None  # only set when stage1_passed is True


@dataclass
class MatchingSummary:
    track_id: UUID
    track_name: str
    total_jobs_considered: int
    stage1_passed: int
    stage1_failed: int
    outcomes: list[MatchOutcome] = field(default_factory=list)


def run_matching_for_track(
    user_id: UUID,
    track_id: UUID,
    db: SupabaseClient | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> MatchingSummary:
    """Runs Stage-1 + Stage-2 for one CV track against every job
    currently in the `jobs` table.

    A job that FAILs Stage-1 is never scored and never written to
    user_job_matches -- there's nothing meaningful to score for a job
    the candidate is genuinely ineligible for or unwilling to take.
    Every job that passes Stage-1 (including one where every criterion
    SKIPped) gets scored and its match row upserted, even at a low
    score -- a low real score is still useful signal, unlike a
    Stage-1 FAIL which isn't a scoring question at all.

    organization_id is read from track.organization_id (see this
    module's docstring) and used for both the match upsert and, after a
    passing match is scored, maybe_auto_apply() (migration 0009), which
    checks the track's auto-apply config and creates a queued
    application if it clears the threshold. Best-effort -- an
    auto-apply failure for one job never stops matching for the rest;
    see maybe_auto_apply's own docstring.

    on_progress, if given, is called as on_progress(jobs_done, jobs_total)
    after every job (pass or fail) -- stays a no-op by default so the
    service itself never prints; scripts/run_matching.py supplies a
    real callback so the CLI isn't silent for the several minutes this
    can take on ~3000 jobs (Stage-2 embedding + two Supabase round-trips
    per upsert_match() call, for every job that passes Stage 1).
    """
    db = db or SupabaseClient(use_service_role=True)

    profile_repo = ProfileRepository(db)
    track_repo = TrackRepository(db)
    job_repo = JobRepository(db)
    match_repo = UserJobMatchRepository(db)

    profile = profile_repo.get_profile_by_user(user_id)
    if profile is None:
        raise ValueError(f"No candidate_profiles row for user_id={user_id}")

    full_profile = profile_repo.get_full_profile(user_id)

    track = track_repo.get_track(track_id)
    if track is None:
        raise ValueError(f"No cv_tracks row for track_id={track_id}")
    if track.organization_id is None:
        # Should be unreachable -- cv_tracks.organization_id has been
        # NOT NULL since migration 0007 -- but this is the write path
        # that broke silently last time a NOT NULL assumption like this
        # one went unchecked (see matching/repository.py's docstring),
        # so fail loudly here rather than let a None reach upsert_match.
        raise ValueError(f"cv_tracks row {track_id} has no organization_id")
    organization_id = track.organization_id

    jobs = job_repo.list_all()

    outcomes: list[MatchOutcome] = []
    stage1_passed = 0
    stage1_failed = 0
    total_jobs = len(jobs)

    for i, job in enumerate(jobs, start=1):
        results = run_stage1_filters(track, job, profile)

        if not passes_stage1(results):
            stage1_failed += 1
            outcomes.append(
                MatchOutcome(
                    job_id=job.id,
                    job_title=job.title,
                    stage1_passed=False,
                    stage1_results=results,
                )
            )
            if on_progress is not None:
                on_progress(i, total_jobs)
            continue

        stage1_passed += 1
        job_text = build_job_text(job.title, job.company, job.description)
        score = compute_match_score(full_profile, track, job_text)
        score *= compute_industry_mismatch_penalty(track, job)

        match_repo.upsert_match(
            user_id=user_id,
            job_id=job.id,
            cv_track_id=track_id,
            match_score=score,
            organization_id=organization_id,
        )

        try:
            maybe_auto_apply(
                db=db,
                user_id=user_id,
                track=track,
                job=job,
                match_score=score,
                full_profile=full_profile,
                organization_id=organization_id,
            )
        except Exception:
            # Best-effort, same reasoning as inside maybe_auto_apply itself
            # -- an auto-apply problem for one job must never abort
            # matching for the rest of the ~3000-job run.
            pass

        outcomes.append(
            MatchOutcome(
                job_id=job.id,
                job_title=job.title,
                stage1_passed=True,
                stage1_results=results,
                match_score=score,
            )
        )

        if on_progress is not None:
            on_progress(i, total_jobs)

    return MatchingSummary(
        track_id=track_id,
        track_name=track.track_name,
        total_jobs_considered=len(jobs),
        stage1_passed=stage1_passed,
        stage1_failed=stage1_failed,
        outcomes=outcomes,
    )


def run_matching_for_track_tracked(
    user_id: UUID,
    track_id: UUID,
    run_id: UUID,
    db: SupabaseClient,
) -> None:
    """Wraps run_matching_for_track with status tracking in matching_runs,
    for the background-task path triggered by POST /tracks/{id}/match.
    Not used by scripts/run_matching.py -- that CLI has no run_id and
    prints its own progress instead.

    Writes progress every 50 jobs (same throttle cadence as
    scripts/run_matching.py's _print_progress, so a CLI run and an API
    run hit Supabase at the same rate) via MatchingRunRepository, then
    marks the run completed or failed. db must be user-scoped (not
    service_role) since MatchingRunRepository relies on matching_runs'
    RLS policy, same rule as UserJobMatchRepository and the existing
    call in tracks.py's trigger_matching().

    user_id here is the CANDIDATE's id (track.user_id), not necessarily
    the caller who triggered the run -- see tracks.py's trigger_matching()
    for the assignment-aware fix this depends on. organization_id is no
    longer a parameter here; run_matching_for_track reads it from the
    track itself.
    """
    run_repo = MatchingRunRepository(db)

    def _on_progress(done: int, total: int) -> None:
        if done % 50 != 0 and done != total:
            return
        run_repo.update_progress(run_id, jobs_processed=done, jobs_total=total)

    try:
        run_matching_for_track(user_id, track_id, db=db, on_progress=_on_progress)
        run_repo.mark_completed(run_id)
    except Exception as exc:
        run_repo.mark_failed(run_id, str(exc))
        raise
