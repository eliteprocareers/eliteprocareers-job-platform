"""
v13 fix verification script. Paste-and-run as-is (no placeholders).
Run on the fix/pm-saas-job-title-weight branch, inside the venv.

Baselines (current live scores, pulled via Supabase this session):
  Canary (false positive, insurance):
    "Assistant Manager – Product Development" @ NCBA Group -> 0.5677
  True positives (real SaaS PM roles, currently under-scoring):
    "Senior Product Manager - Ad Fraud and Identity Solutions" @ Cloudflare -> 0.2800
    "Senior Product Manager - Enterprise (API & SDK)" @ Cloudflare        -> 0.2738
    "Senior Product Manager - FinTech" @ Cloudflare                       -> 0.2401

Expected direction after the fix: canary score DROPS, Cloudflare PM
scores RISE (or at minimum don't drop). If canary doesn't drop, or the
Cloudflare scores drop further, the fix doesn't work -- report back the
numbers rather than merging.
"""

from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository
from eliteprocareers.scoring.embeddings import (
    build_job_description_text,
    build_job_title_text,
    compute_match_score,
)

USER_ID = UUID("43324cff-f36c-404a-bd6a-873bc6bfc050")
PM_SAAS_TRACK_ID = UUID("abff642a-99eb-41c3-a0a2-96739f3a2500")

JOB_IDS = {
    "CANARY (insurance, false positive) NCBA Group": (
        UUID("f1b23a98-5c60-4f4f-93b4-9b6d2f7be1da"),
        0.5677,
    ),
    "Senior PM - Ad Fraud/Identity @ Cloudflare": (
        UUID("d7560d49-a2d0-4e49-9ecb-93dbdb2a58cc"),
        0.2800,
    ),
    "Senior PM - Enterprise API/SDK @ Cloudflare": (
        UUID("c9472a7f-e878-4103-959d-c030ca981857"),
        0.2738,
    ),
    "Senior PM - FinTech @ Cloudflare": (
        UUID("94944d82-5a88-4400-bd13-c5712379b336"),
        0.2401,
    ),
}

db = SupabaseClient(use_service_role=True)
profile_repo = ProfileRepository(db)
track_repo = TrackRepository(db)
job_repo = JobRepository(db)

full_profile = profile_repo.get_full_profile(USER_ID)
track = track_repo.get_track(PM_SAAS_TRACK_ID)

job_ids = [v[0] for v in JOB_IDS.values()]
jobs_by_id = {j.id: j for j in job_repo.get_jobs_by_ids(job_ids)}

print(f"{'Job':55s} {'baseline':>10s} {'new':>10s} {'delta':>10s}")
print("-" * 90)
for label, (job_id, baseline) in JOB_IDS.items():
    job = jobs_by_id.get(job_id)
    if job is None:
        print(f"{label:55s}  NOT FOUND (job_id={job_id})")
        continue
    job_title_text = build_job_title_text(job.title, job.company)
    job_description_text = build_job_description_text(job.description)
    new_score = compute_match_score(
        full_profile, track, job_title_text, job_description_text
    )
    delta = new_score - baseline
    print(f"{label:55s} {baseline:10.4f} {new_score:10.4f} {delta:+10.4f}")

print()
print("Expect: CANARY delta negative, Cloudflare PM deltas positive (or >= 0).")
print("If not, report these numbers back before merging.")
