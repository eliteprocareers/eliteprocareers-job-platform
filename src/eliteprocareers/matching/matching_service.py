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
bypasses that table's per-user RLS policy (user_id = auth.uid()) --
acceptable for this backend-run script since it's explicitly scoped to
one user_id at a time, but a future per-user API endpoint calling this
must NOT reuse service_role for the match-write step; it should
construct a user-scoped SupabaseClient instead, per
matching/repository.py's docstring.
"""
from dataclasses import dataclass, field
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.filtering import (
    CriterionResult,
    passes_stage1,
    run_stage1_filters,
)
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository
from eliteprocareers.scoring.embeddings import build_job_text, compute_match_score


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

    jobs = job_repo.list_all()

    outcomes: list[MatchOutcome] = []
    stage1_passed = 0
    stage1_failed = 0

    for job in jobs:
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
            continue

        stage1_passed += 1
        job_text = build_job_text(job.title, job.company, job.description)
        score = compute_match_score(full_profile, track, job_text)

        match_repo.upsert_match(
            user_id=user_id,
            job_id=job.id,
            cv_track_id=track_id,
            match_score=score,
        )

        outcomes.append(
            MatchOutcome(
                job_id=job.id,
                job_title=job.title,
                stage1_passed=True,
                stage1_results=results,
                match_score=score,
            )
        )

    return MatchingSummary(
        track_id=track_id,
        track_name=track.track_name,
        total_jobs_considered=len(jobs),
        stage1_passed=stage1_passed,
        stage1_failed=stage1_failed,
        outcomes=outcomes,
    )
