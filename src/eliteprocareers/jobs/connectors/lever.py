"""
Lever connector — public Postings API, no auth required.

GET https://api.lever.co/v0/postings/{site}?mode=json

Verified against official docs (github.com/lever/postings-api) AND a live
response from api.lever.co/v0/postings/leverdemo before writing this —
the docs' field table did not list `createdAt`, which does appear in the
real response, so it was confirmed live rather than assumed absent.
"""

from datetime import datetime, timezone

import httpx

from eliteprocareers.jobs.connectors.base import (
    ConnectorCapabilities,
    JobConnector,
    SupportTier,
)
from eliteprocareers.jobs.connectors.registry import registry

BASE_URL = "https://api.lever.co/v0/postings"


@registry.register
class LeverConnector(JobConnector):
    source_name = "lever"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(
        scheduled_polling=True,
        full_job_details=True,
    )
    notes = (
        "Public Postings API, no auth. Verified against official docs "
        "(github.com/lever/postings-api) and a live response from the "
        "'leverdemo' site before implementation. Company name is not in "
        "the API response — caller supplies it alongside the site name, "
        "same pattern as Greenhouse's board_token."
    )

    def fetch_jobs(self, board_token: str, company_name: str, **kwargs) -> list[dict]:
        """Fetch all published postings for a Lever site name.

        Uses `board_token` as the parameter name to match the JobConnector
        call signature the ingestion engine already uses for Greenhouse —
        it holds the Lever "site" value here, e.g. 'netflix'.

        **kwargs absorbs on_source_complete -- see Greenhouse's
        fetch_jobs docstring for why (same reasoning, same connector
        shape: ingestion_service.py already saves after every call here).
        """
        url = f"{BASE_URL}/{board_token}"
        response = httpx.get(url, params={"mode": "json"}, timeout=15.0)
        response.raise_for_status()
        postings = response.json()

        jobs = []
        for posting in postings:
            categories = posting.get("categories") or {}
            created_at_ms = posting.get("createdAt")
            posted_at = (
                datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc).isoformat()
                if created_at_ms is not None
                else None
            )
            jobs.append({
                "source": self.source_name,
                "external_id": str(posting["id"]),
                "company": company_name,
                "title": posting["text"],
                "description": posting.get("descriptionPlain"),
                "url": posting.get("hostedUrl"),
                "location": categories.get("location"),
                "posted_at": posted_at,
                "raw_json": posting,
            })
        return jobs
