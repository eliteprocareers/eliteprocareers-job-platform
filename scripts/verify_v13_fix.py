"""
v14 fix verification script, approach #5. Paste-and-run as-is, no
placeholders. Run on the fix/pm-saas-job-title-weight branch (same
branch, superseded commit -- approach #4/job_title_weight was reverted
after live-verify showed it made the canary WORSE: 0.5677 -> 0.7098).

Baselines (ORIGINAL live scores, i.e. before any v14 change, pulled via
Supabase this session):
  Canary (false positive, insurance):
    "Assistant Manager – Product Development" @ NCBA Group -> 0.5677
    industry tags: ["Banking & Insurance", "Product & Project Management"]
  True positives (real SaaS PM roles, currently under-scoring):
    "Senior Product Manager - Ad Fraud and Identity Solutions" @ Cloudflare -> 0.2800
    "Senior Product Manager - Enterprise (API & SDK)" @ Cloudflare        -> 0.2738
    "Senior Product Manager - FinTech" @ Cloudflare                       -> 0.2401
  (Cloudflare jobs have industry=null -- Greenhouse doesn't populate that
  field -- so compute_industry_mismatch_penalty() is a no-op for them by
  design; they should be unaffected by this fix, not just "still positive".)

PM/SaaS track industries: ["Product & Project Management", "Software & Data"]

Approach #5: instead of tuning embedding text/weights (4 attempts,
v10-v14, all ruled out or reverted), penalize the score post-hoc when a
job's structured industry tags include one the track didn't select. The
NCBA job's "Banking & Insurance" tag isn't in the track's industries;
its "Product & Project Management" tag is (which is why it passes
Stage-1's intentionally-permissive ANY-overlap check) -- the mismatch
penalty targets exactly that gap using clean taxonomy data, not text.

Expected direction: canary score DROPS sharply (embedding score x 0.3).
Cloudflare scores UNCHANGED (no industry data to penalize). If the
canary doesn't drop as expected, or Cloudflare scores change at all,
report back before merging -- the mechanism may not be reading
job.attributes as expected.
"""

from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository
from eliteprocareers.scoring.embeddings import (
    build_job_text,
    compute_industry_mismatch_penalty,
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

print(f"{'Job':55s} {'baseline':>10s} {'raw_new':>10s} {'penalty':>8s} {'final':>10s} {'delta':>10s}")
print("-" * 108)
for label, (job_id, baseline) in JOB_IDS.items():
    job = jobs_by_id.get(job_id)
    if job is None:
        print(f"{label:55s}  NOT FOUND (job_id={job_id})")
        continue
    job_text = build_job_text(job.title, job.company, job.description)
    raw_score = compute_match_score(full_profile, track, job_text)
    penalty = compute_industry_mismatch_penalty(track, job)
    final_score = raw_score * penalty
    delta = final_score - baseline
    print(
        f"{label:55s} {baseline:10.4f} {raw_score:10.4f} {penalty:8.2f} "
        f"{final_score:10.4f} {delta:+10.4f}"
    )

print()
print("Expect: CANARY delta strongly negative (penalty=0.3 applied).")
print("Expect: Cloudflare deltas near zero (penalty=1.0, no industry data).")
print("If not, report these numbers back before merging.")

