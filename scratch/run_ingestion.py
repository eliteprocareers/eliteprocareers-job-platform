"""
Job ingestion script — now driven by the ConnectorRegistry instead of a
hardcoded Greenhouse import. Loops through every registered connector
with scheduled_polling=True, fetches jobs, dedups against the DB, and
bulk-inserts only new postings.

Uses the service_role key (bypasses RLS) — ingestion is a backend
operation, not a per-user action.

Run: python3 scratch/run_ingestion.py
No password needed — reads SUPABASE_SERVICE_ROLE_KEY from .env.
"""

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.jobs.connectors import registry
from eliteprocareers.jobs.known_boards import GREENHOUSE_BOARDS
from eliteprocareers.jobs.known_lever_sites import LEVER_SITES
from eliteprocareers.jobs.repository import JobRepository

# Per-source board/company lists a connector needs to know what to poll.
# Each connector with scheduled_polling=True gets its own entry here as
# it's built.
SOURCE_TARGETS = {
    "greenhouse": GREENHOUSE_BOARDS,
    "lever": LEVER_SITES,
    # Not per-company like Greenhouse/Lever -- BrighterMonday crawls the
    # whole site's /jobs listing pages, so one placeholder entry is
    # enough to make the loop run fetch_jobs() once. board_token/
    # company_name are ignored via **kwargs in fetch_jobs().
    "brightermonday": {"kenya": "BrighterMonday Kenya"},
}


def main():
    db = SupabaseClient(use_service_role=True)
    job_repo = JobRepository(db)

    pollable = registry.with_capability("scheduled_polling")
    print(f"Pollable connectors: {[c.source_name for c in pollable]}")

    grand_total_fetched = 0
    grand_total_new = 0

    for connector_cls in pollable:
        source_name = connector_cls.source_name
        targets = SOURCE_TARGETS.get(source_name)
        if not targets:
            print(f"\n[{source_name}] SKIPPED — no target list wired up in SOURCE_TARGETS yet.")
            continue

        print(f"\n=== {source_name} ===")
        connector = connector_cls()

        existing_ids = job_repo.get_existing_external_ids(source_name)
        print(f"  {len(existing_ids)} already stored.")

        failed_targets = []
        source_fetched = 0
        source_new = 0

        for token, company_name in targets.items():
            try:
                jobs = connector.fetch_jobs(board_token=token, company_name=company_name)
            except Exception as e:
                print(f"  [{token}] FAILED to fetch: {e}")
                failed_targets.append(token)
                continue

            source_fetched += len(jobs)
            new_jobs = [j for j in jobs if j["external_id"] not in existing_ids]
            existing_ids.update(j["external_id"] for j in new_jobs)

            saved = job_repo.bulk_create(new_jobs)
            source_new += len(saved)
            print(f"  [{token}] {len(jobs)} fetched, {len(saved)} new saved")

        print(f"  --- {source_name} summary: {source_fetched} fetched, {source_new} new, failed={failed_targets or 'none'}")
        grand_total_fetched += source_fetched
        grand_total_new += source_new

    print("\n=== INGESTION SUMMARY (all sources) ===")
    print(f"Total jobs fetched: {grand_total_fetched}")
    print(f"Total NEW jobs saved: {grand_total_new}")


if __name__ == "__main__":
    main()
