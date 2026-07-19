#!/usr/bin/env python3
"""
Thin CLI entry point for running Stage-1 + Stage-2 matching for one
CV track against every job in the `jobs` table. All business logic
lives in eliteprocareers.matching.matching_service.run_matching_for_track().

Usage:
    python3 scripts/run_matching.py <user_id> <track_id>
"""
import sys
import time
from uuid import UUID

from eliteprocareers.matching.matching_service import run_matching_for_track


def _print_progress(done: int, total: int, start_time: float) -> None:
    """Prints an in-place progress line every 50 jobs (and always on the
    last job) -- run_matching_for_track() does one embedding pass plus
    up to two Supabase round-trips per job that clears Stage 1, so on
    ~3000 jobs this can run for several minutes with nothing else on
    screen. Every-job printing would just be different noise, so this
    throttles to a readable cadence instead.
    """
    if done % 50 != 0 and done != total:
        return
    elapsed = time.monotonic() - start_time
    rate = done / elapsed if elapsed > 0 else 0
    print(
        f"\r  {done}/{total} jobs processed  ({rate:.1f}/s, {elapsed:.0f}s elapsed)",
        end="",
        flush=True,
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/run_matching.py <user_id> <track_id>")
        return 1

    user_id = UUID(sys.argv[1])
    track_id = UUID(sys.argv[2])

    start_time = time.monotonic()
    summary = run_matching_for_track(
        user_id,
        track_id,
        on_progress=lambda done, total: _print_progress(done, total, start_time),
    )
    print()  # move past the in-place progress line before the summary

    print(f"Track: {summary.track_name}")
    print(f"Total jobs considered: {summary.total_jobs_considered}")
    print(f"Stage-1 passed (scored): {summary.stage1_passed}")
    print(f"Stage-1 failed (skipped scoring): {summary.stage1_failed}")
    print()

    top = sorted(
        (o for o in summary.outcomes if o.stage1_passed),
        key=lambda o: o.match_score,
        reverse=True,
    )[:10]
    print("Top 10 matches:")
    for o in top:
        print(f"  {o.match_score:.4f}  {o.job_title}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
