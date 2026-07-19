"""
BrighterMonday connector — job detail pages embed a Schema.org JobPosting
inside a JSON-LD @graph, intentionally published for Google for Jobs
indexing (confirmed live, not reverse-engineered).

Verified against a real listing (2026-07-19):
https://www.brightermonday.co.ke/listings/sales-personnel-qzqzep

Important: this is a cross-referenced @graph, not a flat JobPosting
object like Greenhouse/Lever return. hiringOrganization and jobLocation
on the JobPosting node are themselves bare {"@id": ...} references that
must be resolved against other nodes in the same @graph — confirmed by
walking the actual graph rather than assumed from the JobPosting node
alone.

Also confirmed live: BrighterMonday's own PostalAddress node has
streetAddress and addressLocality swapped from their semantic meaning —
streetAddress actually holds the city ("Nairobi"), addressLocality holds
the country ("Kenya"). This connector reads streetAddress + addressCountry
for a human-readable location rather than trusting the field names.

Bulk polling (fetch_jobs): confirmed live 2026-07-19 that /jobs is a
simple paginated listing (?page=2 ... up to ~127 pages, ~2,031 jobs
total, ~16 per page), and every listing links to /listings/{slug} — the
same URL shape extract_from_url() already handles. No separate parser
needed for the listing pages themselves; just extract hrefs and reuse
extract_from_url() per job. max_pages caps how much of the site gets
crawled per run — deliberately conservative rather than pulling all
~127 pages every run, since this is a live site being crawled directly,
not an API meant for bulk polling.
"""

import json
import re

import httpx

from eliteprocareers.jobs.connectors.base import (
    ConnectorCapabilities,
    JobConnector,
    SupportTier,
)
from eliteprocareers.jobs.connectors.registry import registry

JSONLD_PATTERN = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)

LISTING_URL_PATTERN = re.compile(
    r'href="(https://www\.brightermonday\.co\.ke/listings/[a-z0-9-]+)"'
)


def _resolve_ref(graph_index: dict, value):
    """If value is a bare {'@id': ...} reference, look it up in the graph
    index and return the resolved node. Otherwise return value unchanged
    (some fields are inline objects, not references).
    """
    if isinstance(value, dict) and set(value.keys()) == {"@id"}:
        return graph_index.get(value["@id"], value)
    return value


@registry.register
class BrighterMondayConnector(JobConnector):
    source_name = "brightermonday"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(
        scheduled_polling=True,
        url_import=True,
        full_job_details=True,
    )
    notes = (
        "Job detail pages embed Schema.org JobPosting JSON-LD as a "
        "cross-referenced @graph — confirmed live against a real listing "
        "2026-07-19, not assumed from convention. hiringOrganization and "
        "jobLocation are @id references requiring graph resolution, not "
        "inline objects. Bulk polling crawls /jobs?page=N (confirmed "
        "simple pagination, ~127 pages, ~2,031 jobs total 2026-07-19), "
        "collecting /listings/{slug} URLs and reusing extract_from_url() "
        "per job — capped per run via max_pages, since this crawls the "
        "live site directly rather than calling a bulk-designed API."
    )

    BASE_LISTING_URL = "https://www.brightermonday.co.ke/jobs"

    def extract_from_url(self, url: str) -> dict | None:
        """Fetch a single BrighterMonday job listing page and parse its
        JSON-LD @graph into a dict shaped to match the `jobs` table columns.

        Returns None if no JobPosting JSON-LD block is found on the page.
        """
        response = httpx.get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()

        match = JSONLD_PATTERN.search(response.text)
        if not match:
            return None

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

        graph = data.get("@graph", [])
        if not graph:
            return None

        graph_index = {node.get("@id"): node for node in graph if "@id" in node}
        job_node = next((n for n in graph if n.get("@type") == "JobPosting"), None)
        if job_node is None:
            return None

        # Resolve hiringOrganization -> Organization node -> name
        org = _resolve_ref(graph_index, job_node.get("hiringOrganization"))
        company_name = org.get("name") if isinstance(org, dict) else None

        # Resolve jobLocation -> Place node -> address -> PostalAddress node
        place = _resolve_ref(graph_index, job_node.get("jobLocation"))
        location = None
        if isinstance(place, dict):
            address = _resolve_ref(graph_index, place.get("address"))
            if isinstance(address, dict):
                city = address.get("streetAddress")  # holds city, not street — confirmed live
                country = address.get("addressCountry")
                location = ", ".join(part for part in [city, country] if part) or None

        job_id = job_node.get("@id", "")
        external_id = job_id.rsplit("/", 1)[-1] if job_id else url

        return {
            "source": self.source_name,
            "external_id": external_id,
            "company": company_name,
            "title": job_node.get("title"),
            "description": job_node.get("description"),
            "url": url,
            "location": location,
            "posted_at": job_node.get("datePosted"),
            "raw_json": job_node,
        }

    def fetch_jobs(self, max_pages: int = 5, **kwargs) -> list[dict]:
        """Crawl BrighterMonday's /jobs listing pages, collect individual
        listing URLs, and extract each via extract_from_url(). max_pages
        caps how many listing pages get crawled in a single run — with
        ~16 jobs/page, max_pages=5 pulls roughly 80 of the most recent
        postings per run, not the whole ~2,031-job site every time.
        """
        jobs: list[dict] = []
        seen_urls: set[str] = set()

        for page_num in range(1, max_pages + 1):
            page_url = (
                self.BASE_LISTING_URL
                if page_num == 1
                else f"{self.BASE_LISTING_URL}?page={page_num}"
            )
            response = httpx.get(page_url, timeout=15.0, follow_redirects=True)
            if response.status_code != 200:
                break

            listing_urls = set(LISTING_URL_PATTERN.findall(response.text))
            new_urls = listing_urls - seen_urls
            if not new_urls:
                # No new listing URLs on this page — likely past the last
                # real page or hit a duplicate; stop rather than keep
                # requesting pages that add nothing.
                break
            seen_urls |= new_urls

            for listing_url in new_urls:
                job = self.extract_from_url(listing_url)
                if job is not None:
                    jobs.append(job)

        return jobs
