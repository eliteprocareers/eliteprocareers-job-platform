#!/usr/bin/env python3
"""
Backfill: generates and writes ai_rationale for every user_job_matches
row that doesn't have one yet.

Context: ai_rationale has existed on the user_job_matches schema and
domain model since matching/models.py was written, but no code path has
ever populated it (confirmed live 2026-07-20: 0/697 rows had a rationale
before this script existed). generation/match_rationale.py does the
actual LLM call; this script is the CLI/orchestration layer around it,
same split as run_matching.py vs matching_service.py.

Defaults to a DRY RUN (calls Groq and prints the rationale it would
write, but does not write it). Pass --apply to actually write rows.
Pass --limit N to cap how many rows are processed this run (useful for
a first sanity-check pass before committing to a full ~697-row run,
which costs 697 Groq calls in whichever mode you choose since the LLM
call itself is what needs checking, not just the write).

Usage:
    python3 scripts/backfill_match_rationales.py                # dry run, all rows
    python3 scripts/backfill_match_rationales.py --limit 5       # dry run, first 5
    python3 scripts/backfill_match_rationales.py --apply         # writes for real
    python3 scripts/backfill_match_rationales.py --apply --limit 50
"""
import sys
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.generation.llm_client import LLMError
from eliteprocareers.generation.match_rationale import generate_match_rationale
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository

# Same hardcoded scope as cleanup_stale_matches.py -- James's 2 real
# tracks, the only ones with any match rows today. Not read from a
# "list all users" query since no such repository method exists yet.
USER_ID = UUID("43324cff-f36c-404a-bd6a-873bc6bfc050")
TRACK_IDS = [
    UUID("460271ec-02ab-4483-894a-3fa872803cc7"),  # Supply Chain / Procurement
    UUID("abff642a-99eb-41c3-a0a2-96739f3a2500"),  # Product Management / SaaS
]


def _parse_limit(argv: list[str]) -> int | None:
    if "--limit" not in argv:
        return None
    idx = argv.index("--limit")
    try:
        return int(argv[idx + 1])
    except (IndexError, ValueError):
        raise SystemExit("--limit requires an integer argument, e.g. --limit 50")


def main() -> int:
    argv = sys.argv[1:]
    apply = "--apply" in argv
    limit = _parse_limit(argv)

    db = SupabaseClient(use_service_role=True)
    profile_repo = ProfileRepository(db)
    track_repo = TrackRepository(db)
    job_repo = JobRepository(db)
    match_repo = UserJobMatchRepository(db)

    profile = profile_repo.get_profile_by_user(USER_ID)
    if profile is None:
        raise ValueError(f"No candidate_profiles row for user_id={USER_ID}")
    full_profile = profile_repo.get_full_profile(USER_ID)

    # Load every job once, keyed by id -- same cost-saving pattern as
    # cleanup_stale_matches.py (one list_all() instead of one select per row).
    jobs_by_id = {job.id: job for job in job_repo.list_all()}

    total_processed = 0
    total_written = 0
    total_errors = 0
    total_skipped_no_job = 0

    for track_id in TRACK_IDS:
        if limit is not None and total_processed >= limit:
            break

        track = track_repo.get_track(track_id)
        if track is None:
            print(f"  SKIP: no cv_tracks row for track_id={track_id}")
            continue

        matches = match_repo.list_matches_for_track(track_id)
        missing = [m for m in matches if not m.ai_rationale]
        print(f"{track.track_name}: {len(matches)} matches, {len(missing)} missing rationale")

        for match in missing:
            if limit is not None and total_processed >= limit:
                print(f"  --limit {limit} reached, stopping.")
                break

            job = jobs_by_id.get(match.job_id)
            if job is None:
                print(f"  job_id={match.job_id} no longer exists in jobs table, skipping")
                total_skipped_no_job += 1
                continue

            total_processed += 1
            try:
                rationale = generate_match_rationale(
                    full_profile, track, job, match.match_score or 0.0
                )
            except LLMError as e:
                total_errors += 1
                print(f"  [{total_processed}] ERROR ({job.title} @ {job.company}): {e}")
                continue

            print(f"  [{total_processed}] {job.title} @ {job.company}")
            print(f"      score={match.match_score:.4f}  {rationale}")

            if apply:
                match_repo.update_rationale(match.id, rationale)
                total_written += 1

        print()

    print(f"Total processed (LLM calls made): {total_processed}")
    print(f"Total errors: {total_errors}")
    print(f"Total skipped (job no longer exists): {total_skipped_no_job}")
    if apply:
        print(f"Total written: {total_written}")
    else:
        print("\nDRY RUN -- no rows were written. Re-run with --apply to write these for real.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
