#!/usr/bin/env python3
"""
Diagnostic-only: title-reinforcement experiment (approach #7 candidate).
Does NOT write to user_job_matches -- ranks are computed in-memory only.
Uncommitted by design; formalize into embeddings.py only after review.
"""
import sys
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.filtering import passes_stage1, run_stage1_filters
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository
from eliteprocareers.scoring.embeddings import (
    build_job_text,
    compute_industry_mismatch_penalty,
    compute_match_score,
)

USER_ID = UUID("43324cff-f36c-404a-bd6a-873bc6bfc050")
TRACK_ID = UUID("abff642a-99eb-41c3-a0a2-96739f3a2500")

REFERENCE_JOB_IDS = {
    UUID("d7560d49-a2d0-4e49-9ecb-93dbdb2a58cc"): "PM - Ad Fraud (Cloudflare)",
    UUID("94944d82-5a88-4400-bd13-c5712379b336"): "PM - FinTech (Cloudflare)",
    UUID("dfee5c0a-5d29-4743-8d28-28a0fa6b0488"): "Sales Ops Manager (Cloudflare, noise ref)",
    UUID("96a79700-1c2b-429e-99e4-38202d5a5578"): "Solutions Engineer, Privy (Stripe)",
}


def reinforced_job_text(job) -> str:
    base = build_job_text(job.title, job.company, job.description)
    return f"{base} {job.title}."


def main() -> int:
    db = SupabaseClient(use_service_role=True)
    profile_repo = ProfileRepository(db)
    track_repo = TrackRepository(db)
    job_repo = JobRepository(db)

    profile = profile_repo.get_profile_by_user(USER_ID)
    full_profile = profile_repo.get_full_profile(USER_ID)
    track = track_repo.get_track(TRACK_ID)
    jobs = job_repo.list_all()

    scored = []
    for job in jobs:
        results = run_stage1_filters(track, job, profile)
        if not passes_stage1(results):
            continue
        job_text = reinforced_job_text(job)
        score = compute_match_score(full_profile, track, job_text)
        score *= compute_industry_mismatch_penalty(track, job)
        scored.append((job.id, job.title, score))

    scored.sort(key=lambda t: t[2], reverse=True)
    total = len(scored)

    print(f"Stage-1 passed (scored): {total}")
    print("NOT written to user_job_matches -- in-memory ranking only.\n")

    for rank, (job_id, title, score) in enumerate(scored, start=1):
        if job_id in REFERENCE_JOB_IDS:
            print(f"  {REFERENCE_JOB_IDS[job_id]}: rank {rank}/{total}, score {score:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
