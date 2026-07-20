#!/usr/bin/env python3
"""
One-time cleanup: removes user_job_matches rows that no longer pass
Stage-1 filtering.

Context: the original 1,144 rows (and today's two full matching runs)
were written before Stage-1 filtering existed / before it had real
attribute data to filter on. run_matching_for_track() only ever
upserts a row for a job that currently passes Stage 1 -- it never
deletes a row for a job that USED to pass under looser (or no)
filtering but doesn't anymore. This script closes that gap: re-runs
run_stage1_filters() against every existing match row's underlying
(track, job, profile) and deletes the ones that now FAIL.

Defaults to a DRY RUN. Pass --apply to actually delete rows.

Usage:
    python3 scripts/cleanup_stale_matches.py            # dry run
    python3 scripts/cleanup_stale_matches.py --apply    # deletes for real
"""
import sys
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.filtering import passes_stage1, run_stage1_filters
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository

# James's 2 real tracks -- the only ones with any match rows today.
# Not read from a "list all users" query since no such repository
# method exists yet and there's only one real candidate in the system.
USER_ID = UUID("43324cff-f36c-404a-bd6a-873bc6bfc050")
TRACK_IDS = [
    UUID("460271ec-02ab-4483-894a-3fa872803cc7"),  # Supply Chain / Procurement
    UUID("abff642a-99eb-41c3-a0a2-96739f3a2500"),  # Product Management / SaaS
]


def main() -> int:
    apply = "--apply" in sys.argv[1:]

    db = SupabaseClient(use_service_role=True)
    profile_repo = ProfileRepository(db)
    track_repo = TrackRepository(db)
    job_repo = JobRepository(db)
    match_repo = UserJobMatchRepository(db)

    profile = profile_repo.get_profile_by_user(USER_ID)
    if profile is None:
        raise ValueError(f"No candidate_profiles row for user_id={USER_ID}")

    # Load every job once, keyed by id -- cheaper than one select per match row.
    jobs_by_id = {job.id: job for job in job_repo.list_all()}

    total_checked = 0
    total_stale = 0

    for track_id in TRACK_IDS:
        track = track_repo.get_track(track_id)
        if track is None:
            print(f"  SKIP: no cv_tracks row for track_id={track_id}")
            continue

        matches = match_repo.list_matches_for_track(track_id)
        print(f"{track.track_name}: {len(matches)} existing match rows")

        stale = []
        for match in matches:
            total_checked += 1
            job = jobs_by_id.get(match.job_id)
            if job is None:
                # Job was deleted/archived since this match was scored --
                # also stale, for a different reason. Flag, don't guess.
                print(f"  job_id={match.job_id} no longer exists in jobs table")
                stale.append(match)
                continue

            results = run_stage1_filters(track, job, profile)
            if not passes_stage1(results):
                stale.append(match)

        total_stale += len(stale)
        print(f"  {len(stale)} of {len(matches)} now fail Stage 1 (stale)")

        if apply:
            for match in stale:
                match_repo.delete_match(match.id)
            print(f"  APPLIED: deleted {len(stale)} rows for this track")
        print()

    print(f"Total checked: {total_checked}")
    print(f"Total stale: {total_stale}")
    if not apply:
        print("\nDRY RUN -- no rows were deleted. Re-run with --apply to delete these for real.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
