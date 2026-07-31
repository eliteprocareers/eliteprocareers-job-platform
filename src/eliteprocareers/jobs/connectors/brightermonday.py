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

As of 2026-07-30, also crawls all 26 of BrighterMonday's own "Job
Function" category pages (see CATEGORY_SLUGS) alongside the general
/jobs feed -- not just medical-pharmaceutical. The general feed's
5-most-recent-pages cap structurally under-represents any category
that isn't currently trending in postings, first noticed when a
nursing client's job search turned up almost nothing despite
BrighterMonday having 52 active medical/pharmaceutical listings the
same day; the same gap applies equally to every other category, so
this was generalized rather than left as a one-off nursing fix.
Category depth is capped independently and more conservatively than
the general feed (see CATEGORY_MAX_PAGES) to keep total per-run
request volume bounded now that there are 27 sources instead of 1.
"""

import json
import logging
import re
import time
from typing import Callable

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

logger = logging.getLogger(__name__)


def _resolve_ref(graph_index: dict, value):
    """Look up an @id in the graph index and return the resolved node.

    Confirmed live 2026-07-19: some JobPosting.jobLocation values are a
    HYBRID -- they carry an @id AND their own inline (but incomplete)
    address stub at the same time, while a separate, complete Place node
    with that same @id (properly referencing a full PostalAddress with
    the real city) sits elsewhere in the top-level @graph array. An exact
    single-key match missed this case and used the incomplete inline
    stub instead of the fuller graph node. Any dict carrying an @id is
    now resolved against the graph index first; only falls back to the
    inline value if that @id is not found there.
    """
    if isinstance(value, dict) and "@id" in value:
        resolved = graph_index.get(value["@id"])
        if resolved is not None:
            return resolved
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

    # Confirmed live 2026-07-30 by fetching the real /jobs page and
    # reading its own "Job Function" filter sidebar directly (not
    # guessed) -- this is BrighterMonday's complete category taxonomy,
    # 26 categories, each a genuine profession/function (no meta/junk
    # entries here, unlike MyJobMag's field list -- see myjobmag.py).
    # Spot-checked 3 of the 26 individually (medical-pharmaceutical,
    # legal-services, and the general /jobs page itself) to confirm
    # every category page shares the same ?page=N pagination and
    # /listings/{slug} URL shape -- not assumed to hold for the other 23
    # just because 3 matched, but same site engine/template throughout
    # made that a reasonable inference to build on.
    CATEGORY_SLUGS: list[str] = [
        "accounting-auditing-finance",
        "admin-office",
        "creative-design",
        "building-architecture",
        "consulting-strategy",
        "customer-service-support",
        "engineering-technology",
        "farming-agriculture",
        "food-services-catering",
        "hospitality-leisure",
        "software-data",
        "legal-services",
        "marketing-communications",
        "medical-pharmaceutical",
        "product-project-management",
        "estate-agent-property-management",
        "quality-control-assurance",
        "human-resources",
        "management-business-development",
        "community-social-services",
        "supply-chain-procurement",
        "sales",
        "research-teaching-training",
        "trades-services",
        "driver-transport-services",
        "health-safety",
    ]

    LISTING_SOURCES: list[str] = [BASE_LISTING_URL]
    for _slug in CATEGORY_SLUGS:
        LISTING_SOURCES.append(f"{BASE_LISTING_URL}/{_slug}")
    del _slug

    # Deliberately smaller than the general feed's max_pages (default 5,
    # caller-overridable) and NOT overridable per-call -- with 27 total
    # sources now, letting every category run to the same depth as the
    # general feed would multiply total per-run request volume far more
    # than is reasonable for a live site with no bulk API and no rate
    # limiting in this codebase (checked -- there isn't any). 3 pages
    # (~48 jobs) per category, refreshed every run, favors breadth
    # across professions and recency over exhaustive depth in any one
    # category -- reasonable for a live jobs feed where older postings
    # are more likely stale anyway.
    CATEGORY_MAX_PAGES = 3

    # Politeness delay between requests -- this crawls a live site
    # directly, not a bulk-designed API, and 27 sources is enough
    # request volume that some throttling is the responsible default
    # (there was none before this expansion, which was fine for 2
    # sources but not appropriate at this scale).
    REQUEST_DELAY_SECONDS = 0.2

    def extract_from_url(self, url: str) -> dict | None:
        """Fetch a single BrighterMonday job listing page and parse its
        JSON-LD @graph into a dict shaped to match the `jobs` table columns.

        Returns None if no JobPosting JSON-LD block is found on the page,
        OR if the request itself fails (timeout, connection error, non-2xx
        status) -- added 2026-07-30 after a real timeout on one MyJobMag
        job page crashed an entire run mid-crawl, losing every job already
        fetched (nothing is saved until fetch_jobs returns). One bad page
        out of hundreds shouldn't cost the whole run; same reasoning
        applies here even though this specific crash happened on the
        other connector.
        """
        try:
            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

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
                # Some employers list nationwide "Kenya" with no specific
                # city — confirmed live (Focus Clinical, Elite Offset) —
                # in which case city and country are both just "Kenya".
                # Drop the duplicate rather than showing "Kenya, Kenya".
                parts = [p for p in [city, country] if p]
                if len(parts) == 2 and parts[0] == parts[1]:
                    parts = [parts[0]]
                location = ", ".join(parts) or None

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

    def fetch_jobs(
        self,
        max_pages: int = 5,
        on_source_complete: Callable[[list[dict]], None] | None = None,
        **kwargs,
    ) -> list[dict]:
        """Crawl every configured listing source (LISTING_SOURCES) and
        extract each listing found via extract_from_url(). The general
        feed (BASE_LISTING_URL) is capped at max_pages (default 5, still
        caller-overridable, unchanged from before this expansion); every
        category source is capped at the smaller, fixed
        CATEGORY_MAX_PAGES instead — see that constant's docstring for
        why category depth isn't tied to the max_pages argument. With
        ~16 jobs/page, that's roughly 80 postings from the general feed
        plus up to ~48 per category across 26 categories per run — a lot
        more coverage than the single-source crawl this replaced, still
        bounded rather than attempting the full ~2,031-job site depth on
        every run.

        Each source paginates independently -- a source stops once its
        own page returns no listing URLs at all, or no URLs new to that
        source (real end-of-listings, not just a URL already pulled from
        a different source). A single extracted_urls set is still used
        across all sources so a job appearing in more than one source
        (e.g. a recent nursing post that's both in the general feed and
        the medical-pharmaceutical category) is only extracted once.

        A small delay (REQUEST_DELAY_SECONDS) runs between every HTTP
        request -- listing pages and individual job-detail fetches alike
        -- since this now issues meaningfully more requests per run than
        the 2-source version, and there's still no other rate limiting
        anywhere in this codebase.

        on_source_complete, if given, is called once after each source
        finishes (with just that source's newly extracted jobs) -- added
        2026-07-31 after a real run lost 100% of a source's crawled jobs
        when the process was killed mid-crawl (laptop closed), since
        ingestion_service.py previously only saved anything after this
        whole method returned. A 27-or-46-source crawl at this depth can
        run for the better part of an hour; nothing about that should be
        all-or-nothing. This method still also returns the full
        accumulated list at the end regardless, so existing callers
        (the smoke test, anything not passing this callback) keep
        working exactly as before -- this is additive, not a breaking
        change to the return contract.
        """
        jobs: list[dict] = []
        extracted_urls: set[str] = set()

        for source_index, base_url in enumerate(self.LISTING_SOURCES, start=1):
            source_seen: set[str] = set()
            source_jobs: list[dict] = []
            source_max_pages = max_pages if base_url == self.BASE_LISTING_URL else self.CATEGORY_MAX_PAGES
            logger.info(
                "BrighterMonday source %d/%d: %s (max_pages=%d)",
                source_index, len(self.LISTING_SOURCES), base_url, source_max_pages,
            )

            for page_num in range(1, source_max_pages + 1):
                page_url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
                time.sleep(self.REQUEST_DELAY_SECONDS)
                try:
                    response = httpx.get(page_url, timeout=15.0, follow_redirects=True)
                except httpx.HTTPError:
                    # Same reasoning as extract_from_url's try/except -- a
                    # failed listing-page request stops just this source's
                    # pagination (same as a real end-of-listings), not the
                    # whole run.
                    break
                if response.status_code != 200:
                    break

                listing_urls = set(LISTING_URL_PATTERN.findall(response.text))
                if not listing_urls:
                    break

                new_to_source = listing_urls - source_seen
                if not new_to_source:
                    # No URLs new to THIS source's own pagination — real
                    # end of listings or a repeated page. Doesn't trigger
                    # just because another source already extracted the
                    # same URLs (see extracted_urls check below).
                    break
                source_seen |= new_to_source

                for listing_url in new_to_source:
                    if listing_url in extracted_urls:
                        continue
                    extracted_urls.add(listing_url)
                    time.sleep(self.REQUEST_DELAY_SECONDS)
                    job = self.extract_from_url(listing_url)
                    if job is not None:
                        source_jobs.append(job)

            jobs.extend(source_jobs)
            if on_source_complete is not None and source_jobs:
                on_source_complete(source_jobs)

        return jobs
