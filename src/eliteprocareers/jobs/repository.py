"""
JobRepository — CRUD + dedup-aware bulk ingestion for the `jobs` table.

Dedup strategy: rather than inserting one row at a time and catching
unique-constraint violations, fetch the set of external_ids already
stored for a given source once, filter new postings against that set
in Python, and bulk-insert only what's actually new.
"""

import logging

from eliteprocareers.db.client import SupabaseClient, SupabaseError
from eliteprocareers.jobs.models import Job

logger = logging.getLogger(__name__)


class JobRepository:
    TABLE = "jobs"

    def __init__(self, db: SupabaseClient):
        self.db = db

    def get_existing_external_ids(self, source: str) -> set[str]:
        """All external_ids already stored for this source (e.g. 'greenhouse').

        Paginates via limit/offset — PostgREST caps unpaginated GET responses
        at 1000 rows by default, which silently truncated this for any source
        with more than 1000 stored jobs. Loops until a page comes back short.
        """
        page_size = 1000
        offset = 0
        all_ids: set[str] = set()

        while True:
            rows = self.db.select(
                self.TABLE,
                params={
                    "select": "external_id",
                    "source": f"eq.{source}",
                    "limit": page_size,
                    "offset": offset,
                },
            )
            all_ids.update(row["external_id"] for row in rows)
            if len(rows) < page_size:
                break
            offset += page_size

        return all_ids

    def bulk_create(self, jobs: list[dict]) -> list[Job]:
        """Insert a list of job payload dicts (already deduped by the caller)
        as-is. Each dict must match the jobs table columns (minus id/ingested_at,
        which default in the DB). Returns the inserted rows as Job objects.

        Tries a single batch INSERT first (fast path). If that fails --
        e.g. one row violates a NOT NULL constraint, which previously
        killed the entire batch including valid rows (confirmed live with
        MyJobMag's "Transport Manager" listing, company=None) -- falls back
        to inserting one row at a time, logging and skipping only the rows
        that actually fail, so one bad row from imperfect connector parsing
        can never take down an otherwise-valid batch.
        """
        if not jobs:
            return []

        try:
            rows = self.db.insert(self.TABLE, jobs)
            return [Job.model_validate(row) for row in rows]
        except SupabaseError as batch_error:
            logger.warning(
                "bulk_create: batch insert of %d rows failed (%s) -- "
                "falling back to one-row-at-a-time",
                len(jobs),
                batch_error,
            )

        saved: list[Job] = []
        for job in jobs:
            try:
                rows = self.db.insert(self.TABLE, job)
                saved.extend(Job.model_validate(row) for row in rows)
            except SupabaseError as row_error:
                logger.warning(
                    "bulk_create: skipped row (source=%s, external_id=%s): %s",
                    job.get("source"),
                    job.get("external_id"),
                    row_error,
                )
        return saved

    def list_by_source(self, source: str) -> list[Job]:
        rows = self.db.select(self.TABLE, params={"select": "*", "source": f"eq.{source}"})
        return [Job.model_validate(row) for row in rows]
