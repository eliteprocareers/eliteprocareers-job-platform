#!/usr/bin/env python3
"""
One-time migration: sets CVTrack.industries for every cv_tracks row
whose track_name has an entry in taxonomy/industries.py's
CV_TRACK_NAME_MAP, so check_industry has real candidate-side data to
match against (previously every track had industries=[], meaning
check_industry SKIPped for every job regardless of attributes.industry
being populated).

Only touches rows whose track_name is a key in CV_TRACK_NAME_MAP --
never guesses a mapping for a track name it doesn't recognize. A track
not in the map is reported, not silently left alone without saying so.

Defaults to a DRY RUN. Pass --apply to actually PATCH the rows.

Usage:
    python3 scripts/migrate_track_industries.py            # dry run
    python3 scripts/migrate_track_industries.py --apply    # writes for real
"""
import sys

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.taxonomy.industries import CV_TRACK_NAME_MAP


def fetch_all_tracks(db: SupabaseClient) -> list[dict]:
    page_size = 1000
    offset = 0
    rows: list[dict] = []

    while True:
        page = db.select(
            "cv_tracks",
            params={
                "select": "id,track_name,industries",
                "limit": page_size,
                "offset": offset,
            },
        )
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    return rows


def main() -> int:
    apply = "--apply" in sys.argv[1:]

    db = SupabaseClient(use_service_role=True)
    tracks = fetch_all_tracks(db)
    print(f"Fetched {len(tracks)} cv_tracks rows.\n")

    matched = 0
    unmatched: list[str] = []
    updated = 0

    for track in tracks:
        track_name = track["track_name"]
        if track_name not in CV_TRACK_NAME_MAP:
            unmatched.append(track_name)
            continue

        matched += 1
        new_industries = CV_TRACK_NAME_MAP[track_name]
        current_industries = track.get("industries") or []

        print(f"  {track_name!r}")
        print(f"    current:  {current_industries}")
        print(f"    proposed: {new_industries}")

        if apply and current_industries != new_industries:
            db.update("cv_tracks", {"industries": new_industries}, {"id": f"eq.{track['id']}"})
            updated += 1

    print()
    print(f"Matched (in CV_TRACK_NAME_MAP): {matched}")
    if unmatched:
        print(f"NOT in CV_TRACK_NAME_MAP (left untouched, add if these need industries set):")
        for name in unmatched:
            print(f"  {name!r}")
    print()

    if apply:
        print(f"APPLIED: updated {updated} rows.")
    else:
        print(
            "DRY RUN -- no rows were written. "
            "Re-run with --apply to write these industries for real."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
