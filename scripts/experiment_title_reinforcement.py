#!/usr/bin/env python3
"""
SUPERSEDED (v17/v18): this diagnostic produced the numbers behind approach
#7 (title-reinforcement), which has since been ACCEPTED and formalized
directly into build_job_text() in scoring/embeddings.py -- see that
function's docstring for the full decision, tradeoffs, and the specific
noise regression (Sales Ops Manager, Cloudflare: rank 58 -> 7/348) that
was knowingly accepted.

Kept here, unchanged, as a live re-verification tool: since
reinforced_job_text() below now duplicates what build_job_text() already
does internally, this script's own reinforcement step is redundant against
current code (double-reinforcement), but it remains useful for re-running
the original 4-job comparison against a *future* build_job_text() change,
to check whether a later fix regresses this decision. Does NOT write to
user_job_matches -- ranks are computed in-memory only.
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
    # build_job_text() now reinforces the title internally (approach #7,
    # accepted v17/v18) -- no extra repetition needed here anymore.
    return build_job_text(job.title, job.company, job.description)


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
