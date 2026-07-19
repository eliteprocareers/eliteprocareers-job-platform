#!/usr/bin/env python3
"""
Thin CLI entry point for job ingestion. Loads config, initializes
logging, invokes the ingestion service, reports results, sets the exit
code. All business logic lives in
eliteprocareers.jobs.ingestion_service.run_ingestion().
"""
import logging
import sys

from eliteprocareers.jobs.ingestion_service import run_ingestion

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    summary = run_ingestion()

    print(f"Pollable connectors: {summary.pollable_sources}\n")

    any_failures = False
    for r in summary.results:
        if r.skipped_reason:
            print(f"[{r.source}] SKIPPED — {r.skipped_reason}\n")
            continue

        print(f"=== {r.source} ===")
        print(f"  {r.fetched} fetched, {r.new_saved} new saved")
        if r.failed_targets:
            any_failures = True
            print(f"  failed: {r.failed_targets}")
        print()

    print("=== INGESTION SUMMARY (all sources) ===")
    print(f"Total jobs fetched: {summary.total_fetched}")
    print(f"Total NEW jobs saved: {summary.total_new}")

    return 1 if any_failures else 0


if __name__ == "__main__":
    sys.exit(main())
