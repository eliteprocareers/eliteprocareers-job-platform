#!/usr/bin/env python3
"""
Diagnostic for the §1i match-quality false-positive observation
(handover v38): on Jane Akinyi Orimba's nursing track, several
clearly non-nursing roles (HR and Facility Officer 0.433, In-House
Recruiter 0.409, Coordinator/Vetting 0.408, Travel Advisor 0.393)
scored close enough to genuine nursing matches (top score 0.556) to
land in her top-15.

v39 code-review session (no live DB access) traced two existing
anti-noise mechanisms that are both keyed off CVTrack.industries:

  1. filtering.check_industry() -- Stage-1 FAILs a job outright if
     it has industry tags with zero overlap with track.industries,
     but only when track.industries is non-empty. Empty is a
     deliberate no-op SKIP ("no preference").
  2. scoring.embeddings.compute_industry_mismatch_penalty() -- applies
     a 0.3x penalty to jobs that partially overlap track.industries
     but also carry an unselected tag. Also an explicit no-op (returns
     1.0) when track.industries is empty.

CVTrack.industries defaults to [] (profiles/models.py), and
TrackForm.tsx's industries input has no `required` attribute (unlike
track_name, which does) -- so a candidate can finish track creation
without ever setting one, silently disabling BOTH mechanisms above.

THIS IS AN UNVERIFIED HYPOTHESIS. This script exists to confirm or
rule it out against Jane's real track/job/match rows before any
scoring or product change ships -- per this project's verification
discipline (every write checked against real data, not just plausible
code-reading). Do not treat the reasoning above as fact until this
script has actually been run.

Usage:
    python3 scripts/investigate_industry_false_positives.py <user_id> <track_id>

If Jane's user_id/track_id aren't already known, find them first:
    SELECT id, user_id, track_name, industries FROM cv_tracks
    WHERE track_name ILIKE '%nurs%';
"""
import sys
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.filtering import check_industry
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.track_repository import TrackRepository
from eliteprocareers.scoring.embeddings import compute_industry_mismatch_penalty

# The four titles named in §1i, for quick visual identification in
# the printed match list -- matching is substring/case-insensitive,
# not an exhaustive or authoritative list of every false positive.
_FLAGGED_TITLES = [
    "hr and facility officer",
    "in-house recruiter",
    "coordinator/vetting",
    "travel advisor",
]


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/investigate_industry_false_positives.py <user_id> <track_id>")
        return 1

    user_id = UUID(sys.argv[1])
    track_id = UUID(sys.argv[2])

    db = SupabaseClient(use_service_role=True)
    track_repo = TrackRepository(db)
    job_repo = JobRepository(db)
    match_repo = UserJobMatchRepository(db)

    track = track_repo.get_track(track_id)
    if track is None:
        print(f"No cv_tracks row for track_id={track_id}")
        return 1

    print("=" * 70)
    print(f"Track: {track.track_name!r} (id={track.id})")
    print(f"  target_roles: {track.target_roles}")
    print(f"  industries:   {track.industries!r}")
    print("=" * 70)

    if not track.industries:
        print(
            "\n>>> CONFIRMED: track.industries is empty. Both "
            "check_industry() (Stage-1) and compute_industry_mismatch_"
            "penalty() (Stage-2) are no-ops for this track -- neither "
            "anti-noise mechanism can be responsible for filtering "
            "false positives here, by design. This directly supports "
            "the empty-industries hypothesis.\n"
        )
    else:
        print(
            "\n>>> track.industries is NOT empty. The empty-industries "
            "hypothesis is RULED OUT for this track -- the false "
            "positives are getting through some other way (e.g. the "
            "flagged jobs' industry tags genuinely do overlap "
            "track.industries, or those jobs have no industry "
            "attribute at all). Re-investigate before proposing a fix.\n"
        )

    matches = match_repo.list_matches_for_track(track_id)
    print(f"Total scored matches for this track: {len(matches)}")

    all_jobs = {j.id: j for j in job_repo.list_all()}

    top15 = matches[:15]
    print("\nTop 15 matches:")
    print("-" * 70)
    for m in top15:
        job = all_jobs.get(m.job_id)
        title = job.title if job else "<job not found>"
        flagged = any(f in title.lower() for f in _FLAGGED_TITLES)
        marker = "  <-- FLAGGED IN §1i" if flagged else ""
        industry_tag = job.attributes.get("industry") if job else None
        print(f"  {m.match_score:.4f}  {title}{marker}")
        if job is not None:
            print(f"           industry attribute: {industry_tag!r}")
            if track.industries:
                result = check_industry(track, job)
                penalty = compute_industry_mismatch_penalty(track, job)
                print(f"           check_industry: {result.outcome.value} ({result.detail})")
                print(f"           industry_mismatch_penalty: {penalty}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
