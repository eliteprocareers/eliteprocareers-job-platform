#!/usr/bin/env python3
"""
Exports a candidate's top matches for one CV track into a plain-text
list James (or anyone) can actually read and act on -- title, company,
location, match score, and the real apply URL for each job.

This is a stopgap, not a dashboard: there's no UI or auto-apply system
in this platform yet. Matching already produces real ranked results in
user_job_matches; this script is the shortest path from "data sitting
in Supabase" to "something James can actually use to start applying."

Usage:
    python3 scripts/export_top_matches.py <user_id> <track_id> [options]

Options:
    --top N          How many matches to include (default: 20)
    --min-score S    Only include matches scoring >= S (default: no floor)
    --output PATH    Write the list to a file as well as printing it
"""
import argparse
import sys
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.track_repository import TrackRepository


def format_matches(track_name: str, entries: list[dict]) -> str:
    lines = [f"Top matches -- {track_name}", "=" * 60, ""]

    for i, entry in enumerate(entries, start=1):
        job = entry["job"]
        score = entry["match_score"]
        lines.append(f"{i}. [{score:.3f}] {job.title} -- {job.company}")
        if job.location:
            lines.append(f"   Location: {job.location}")
        if job.url:
            lines.append(f"   Apply: {job.url}")
        else:
            lines.append("   Apply: (no URL on file for this job -- check the source site directly)")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export top matches for a CV track")
    parser.add_argument("user_id", type=UUID)
    parser.add_argument("track_id", type=UUID)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    db = SupabaseClient(use_service_role=True)
    track_repo = TrackRepository(db)
    match_repo = UserJobMatchRepository(db)
    job_repo = JobRepository(db)

    track = track_repo.get_track(args.track_id)
    if track is None:
        print(f"No cv_tracks row for track_id={args.track_id}", file=sys.stderr)
        return 1

    matches = match_repo.list_matches_for_track(args.track_id, min_score=args.min_score)
    top_matches = [m for m in matches if m.user_id == args.user_id][: args.top]

    if not top_matches:
        print(f"No matches found for track {track.track_name!r}.")
        return 0

    jobs = job_repo.get_jobs_by_ids([m.job_id for m in top_matches])
    jobs_by_id = {j.id: j for j in jobs}

    entries = []
    for m in top_matches:
        job = jobs_by_id.get(m.job_id)
        if job is None:
            # Job was deleted/re-ingested since this match was scored --
            # skip rather than crash on a stale reference.
            continue
        entries.append({"job": job, "match_score": m.match_score})

    output_text = format_matches(track.track_name, entries)
    print(output_text)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text)
        print(f"\nAlso written to {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
