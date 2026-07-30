"""
Standalone smoke test for the BrighterMonday and MyJobMag connectors'
category expansion (2026-07-30, now 27 and 46 listing sources
respectively -- general feed + curated professional categories).
Deliberately needs NO Supabase/Gemini/Groq credentials -- these
connectors' fetch_jobs() only needs outbound internet access, so this
can run before committing to a full ingestion pass. Run from the repo
root:

    python3 scripts/smoke_test_connectors.py

max_pages=1 here is deliberately light -- this is a sanity check that
every configured source resolves and parses correctly, not a real
ingestion run. A real run uses each connector's own defaults (general
feed capped by the max_pages argument, default 5; every category
capped independently at CATEGORY_MAX_PAGES=3) via
scripts/run_ingestion.py.

Sandbox note: this can't be run from the Claude session's own sandbox
(egress allowlist is package/git infra only, confirmed via a real 403
host_not_allowed from the egress proxy) -- needs to run somewhere with
real internet access, e.g. locally.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eliteprocareers.jobs.connectors.brightermonday import BrighterMondayConnector
from eliteprocareers.jobs.connectors.myjobmag import MyJobMagConnector


def run(name: str, connector, max_pages: int = 1) -> None:
    source_count = len(connector.LISTING_SOURCES)
    print(f"\n=== {name} ({source_count} sources, max_pages={max_pages}) ===")
    jobs = connector.fetch_jobs(max_pages=max_pages)
    print(f"Total jobs fetched: {len(jobs)}")

    healthcare_keywords = ("nurse", "nursing", "clinical", "medical", "health", "pharma")
    healthcare_jobs = [
        j for j in jobs
        if any(k in (j.get("title") or "").lower() for k in healthcare_keywords)
    ]
    print(f"Healthcare-relevant (by title): {len(healthcare_jobs)}")

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
    print("Note: max_pages=1 here undercounts what a real run will pull --")
    print("this is just confirming every source resolves and parses, not volume.")

