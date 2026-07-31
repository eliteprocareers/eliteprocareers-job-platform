"""
Ingestion service — polls every registered connector with
scheduled_polling=True, dedups against the DB, and bulk-inserts new
postings. Pure application logic: no printing, no argv, no process exit
codes. Callable from scripts/run_ingestion.py, tests, a scheduled worker,
or an API endpoint.

Uses the service_role key (bypasses RLS) — ingestion is a backend
operation, not a per-user action.
"""
from dataclasses import dataclass, field

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
    "myjobmag": {"kenya": "MyJobMag Kenya"},
}


@dataclass
class SourceResult:
    source: str
    fetched: int = 0
    new_saved: int = 0
    failed_targets: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


@dataclass
class IngestionSummary:
    pollable_sources: list[str]
    results: list[SourceResult]

    @property
    def total_fetched(self) -> int:
        return sum(r.fetched for r in self.results)

    @property
    def total_new(self) -> int:
        return sum(r.new_saved for r in self.results)


def run_ingestion(db: SupabaseClient | None = None) -> IngestionSummary:
    db = db or SupabaseClient(use_service_role=True)
    job_repo = JobRepository(db)

    pollable = registry.with_capability("scheduled_polling")
    results: list[SourceResult] = []

    for connector_cls in pollable:
        source_name = connector_cls.source_name
        targets = SOURCE_TARGETS.get(source_name)

        if not targets:
            results.append(SourceResult(
                source=source_name,
                skipped_reason="no target list wired up in SOURCE_TARGETS yet",
            ))
            continue

        connector = connector_cls()
        result = SourceResult(source=source_name)

        existing_ids = job_repo.get_existing_external_ids(source_name)
        reported_ids: set[str] = set()

        def save_batch(jobs_batch: list[dict]) -> None:
            # Shared by both the on_source_complete callback (fires
            # mid-crawl for BrighterMonday/MyJobMag -- see their
            # fetch_jobs docstrings) and the post-call save below (the
            # only path Greenhouse/Lever actually use, since they save
            # once per board/site already). Added 2026-07-31 after a
            # real run lost an entire source's crawled jobs when the
            # process was killed mid-crawl, since nothing was saved
            # until fetch_jobs() returned as a whole.
            #
            # reported_ids guards against double-counting result.fetched
            # -- BrighterMonday/MyJobMag jobs get reported once via the
            # mid-crawl callback, then appear again in the full list
            # returned at the end (see the post-call save below); without
            # this, every one of their jobs would be counted twice.
            not_yet_reported = [j for j in jobs_batch if j["external_id"] not in reported_ids]
            reported_ids.update(j["external_id"] for j in not_yet_reported)
            result.fetched += len(not_yet_reported)

            new_jobs = [j for j in not_yet_reported if j["external_id"] not in existing_ids]
            existing_ids.update(j["external_id"] for j in new_jobs)
            saved = job_repo.bulk_create(new_jobs)
            result.new_saved += len(saved)

        for token, company_name in targets.items():
            try:
                jobs = connector.fetch_jobs(
                    board_token=token,
                    company_name=company_name,
                    on_source_complete=save_batch,
                )
            except Exception as e:
                result.failed_targets.append(f"{token}: {e}")
                continue

            # For BrighterMonday/MyJobMag, every job in this returned
            # list was already saved AND counted incrementally via the
            # on_source_complete callback above -- reported_ids and
            # existing_ids both already contain their external_ids by
            # this point, so this call correctly becomes a full no-op.
            # For Greenhouse/Lever, which don't call on_source_complete
            # at all (see their fetch_jobs docstrings -- they already
            # save once per board/site via this exact call), this is the
            # only save that happens, same as before this change.
            save_batch(jobs)

        results.append(result)

    return IngestionSummary(
        pollable_sources=[c.source_name for c in pollable],
        results=results,
    )
