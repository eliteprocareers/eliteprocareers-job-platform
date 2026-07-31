"""
Standalone smoke test for the BrighterMonday and MyJobMag connectors'
category expansion (2026-07-30, now 27 and 46 listing sources
respectively -- general feed + curated professional categories).
Deliberately needs NO Supabase/Gemini/Groq credentials -- these
connectors' fetch_jobs() only needs outbound internet access, so this
can run before committing to a full ingestion pass. Run from the repo
root:

    python3 scripts/smoke_test_connectors.py

Deliberately light by design, on two axes:
- max_pages=1 -- confirms every sampled source resolves and parses
  correctly, not real ingestion volume.
- SOURCE_SAMPLE_SIZE -- only crawls a handful of sources per connector
  (general feed + a few categories), not all 73. A real end-to-end run
  of every source at max_pages=1 was timed at ~50 minutes in practice
  (real network latency to Kenya-hosted sites dominates, not the
  connectors' own 0.2s politeness delay) -- far too slow for a quick
  sanity check, whose only job is confirming the code path still works
  after a change, not covering every category every time. A real run
  still crawls every source, at each connector's own default depth, via
  scripts/run_ingestion.py.

Progress logging (INFO level, one line per source) is enabled here so
a run in progress is visibly making progress rather than looking stuck
for its whole duration -- the same logging now fires during a real
run_ingestion.py run too, unconditionally (see brightermonday.py /
myjobmag.py fetch_jobs()).

Sandbox note: this can't be run from the Claude session's own sandbox
(egress allowlist is package/git infra only, confirmed via a real 403
host_not_allowed from the egress proxy) -- needs to run somewhere with
real internet access, e.g. locally.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eliteprocareers.jobs.connectors.brightermonday import BrighterMondayConnector
from eliteprocareers.jobs.connectors.myjobmag import MyJobMagConnector

logging.basicConfig(level=logging.INFO, format="%(message)s")

SOURCE_SAMPLE_SIZE = 5  # general feed + 4 categories, per connector


def run(name: str, connector, max_pages: int = 1, sample_size: int = SOURCE_SAMPLE_SIZE) -> None:
    total_sources = len(connector.LISTING_SOURCES)
    sample = connector.LISTING_SOURCES[:sample_size]
    # Shadows the class attribute on this instance only -- doesn't touch
    # BrighterMondayConnector.LISTING_SOURCES / MyJobMagConnector.
    # LISTING_SOURCES themselves, so a real ingestion run elsewhere in
    # the same process (there isn't one here, but to be safe) would
    # still see the full list.
    connector.LISTING_SOURCES = sample

    print(f"\n=== {name} ({len(sample)} of {total_sources} sources sampled, max_pages={max_pages}) ===")
    jobs = connector.fetch_jobs(max_pages=max_pages)
    print(f"Total jobs fetched: {len(jobs)}")

    healthcare_keywords = ("nurse", "nursing", "clinical", "medical", "health", "pharma")
    healthcare_jobs = [
        j for j in jobs
        if any(k in (j.get("title") or "").lower() for k in healthcare_keywords)
    ]
    print(f"Healthcare-relevant (by title, incidental to this sample): {len(healthcare_jobs)}")

    missing_fields = [
        j for j in jobs
        if not j.get("title") or not j.get("url") or not j.get("external_id")
    ]
    if missing_fields:
        print(f"WARNING: {len(missing_fields)} jobs missing title/url/external_id")

    external_ids = [j["external_id"] for j in jobs]
    dupes = len(external_ids) - len(set(external_ids))
    if dupes:
        print(f"WARNING: {dupes} duplicate external_ids within this run")


if __name__ == "__main__":
    run("BrighterMonday", BrighterMondayConnector())
    run("MyJobMag", MyJobMagConnector())
    print("\nDone. If job counts are meaningfully non-zero and there are no")
    print("WARNINGs above, the connector changes are safe for a real ingestion run.")
    print("Note: this only sampled a few sources at max_pages=1 -- confirming the")
    print("code path works, not real coverage. A real run (scripts/run_ingestion.py)")
    print("crawls every source and will take considerably longer -- expect it to run")
    print("for a while; the per-source log lines above are now what it prints too,")
    print("so it'll be visibly progressing rather than silent the whole time.")

