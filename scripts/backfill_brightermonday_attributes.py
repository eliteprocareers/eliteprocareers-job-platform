#!/usr/bin/env python3
"""
One-time backfill: populates jobs.attributes for every BrighterMonday
job already in the `jobs` table, using
eliteprocareers.jobs.attribute_extraction.extract_brightermonday_attributes()
against each row's existing raw_json. No new HTTP requests -- pure
transform on data already stored. Same shape as
backfill_myjobmag_attributes.py.

Defaults to a DRY RUN. Pass --apply to actually PATCH the rows.

Usage:
    python3 scripts/backfill_brightermonday_attributes.py            # dry run
    python3 scripts/backfill_brightermonday_attributes.py --apply    # writes for real
"""
import sys
from collections import Counter

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.attribute_extraction import extract_brightermonday_attributes


def fetch_brightermonday_rows(db: SupabaseClient) -> list[dict]:
    page_size = 1000
    offset = 0
    rows: list[dict] = []

    while True:
        page = db.select(
            "jobs",
            params={
                "select": "id,title,raw_json",
                "source": "eq.brightermonday",
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
    rows = fetch_brightermonday_rows(db)
    print(f"Fetched {len(rows)} BrighterMonday jobs.\n")

    field_counts: Counter[str] = Counter()
    empty_count = 0
    all_unmapped: Counter[str] = Counter()
    examples: list[tuple[str, dict]] = []
    updated = 0

    for row in rows:
        raw_json = row.get("raw_json") or {}
        attributes, unmapped = extract_brightermonday_attributes(raw_json)
        all_unmapped.update(unmapped)

        if not attributes:
            empty_count += 1
            continue

        for key in attributes:
            field_counts[key] += 1

        if len(examples) < 5:
            examples.append((row["title"], attributes))

        if apply:
            db.update("jobs", {"attributes": attributes}, {"id": f"eq.{row['id']}"})
            updated += 1

    print("Field population counts (out of {} jobs):".format(len(rows)))
    for key, count in field_counts.most_common():
        print(f"  {key:20s} {count}")
    print(f"  {'(no fields extracted)':20s} {empty_count}")
    print()

    if all_unmapped:
        print("UNMAPPED industry/occupationalCategory values (need adding to the taxonomy maps):")
        for value, count in all_unmapped.most_common():
            print(f"  {count:3d}  {value!r}")
        print()
    else:
        print("No unmapped industry/occupationalCategory values.\n")

    print("Example rows:")
    for title, attributes in examples:
        print(f"  {title!r}")
        print(f"    -> {attributes}")
    print()

    if apply:
        print(f"APPLIED: updated {updated} rows.")
    else:
        print(
            "DRY RUN -- no rows were written. "
            "Re-run with --apply to write these attributes for real."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
