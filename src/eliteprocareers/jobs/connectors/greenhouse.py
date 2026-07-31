"""
Greenhouse connector — the reference implementation for the connector
contract. Public, no-auth Job Board API, verified against real API docs
before this was written (not assumed from convention).

GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""

import httpx

from eliteprocareers.jobs.connectors.base import (
    ConnectorCapabilities,
    JobConnector,
    SupportTier,
)
from eliteprocareers.jobs.connectors.registry import registry

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


@registry.register
class GreenhouseConnector(JobConnector):
    source_name = "greenhouse"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(
        scheduled_polling=True,
        full_job_details=True,
        # company_discovery=False: Greenhouse has no directory of its
        # customers, so we rely on a curated board-token list (known_boards.py)
        # rather than discovering companies automatically.
    )
    notes = (
        "Public Job Board API, no auth required. Verified against real "
        "API docs (developers.greenhouse.io) before implementation. "
        "Company name is not in the API response (only board-level) — "
        "caller must supply it alongside the board token."
    )

    def fetch_jobs(self, board_token: str, company_name: str, **kwargs) -> list[dict]:
        """Fetch all published jobs for a Greenhouse board token.

        Returns dicts shaped to match the `jobs` table columns, ready for
        JobRepository.bulk_create() after caller-side dedup filtering.

        **kwargs absorbs on_source_complete (added 2026-07-31 for
        BrighterMonday/MyJobMag's incremental-save callback) -- this
        connector already saves incrementally in practice, since
        ingestion_service.py calls fetch_jobs() once per board and saves
        after each call returns, so there's nothing for this connector
        to call the callback with; it just needs to not break when
        ingestion_service.py passes it uniformly to every connector.
        """
        url = f"{BASE_URL}/{board_token}/jobs"
        response = httpx.get(url, params={"content": "true"}, timeout=15.0)
        response.raise_for_status()
        data = response.json()

        jobs = []
        for job in data.get("jobs", []):
            location = job.get("location") or {}
            jobs.append({
                "source": self.source_name,
                "external_id": str(job["id"]),
                "company": company_name,
                "title": job["title"],
                "description": job.get("content"),
                "url": job.get("absolute_url"),
                "location": location.get("name"),
                "posted_at": job.get("updated_at"),
                "raw_json": job,
            })
        return jobs
