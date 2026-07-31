"""
MyJobMag Kenya connector — no JSON-LD (unlike BrighterMonday, confirmed
live 2026-07-19), but a consistent, predictable HTML template across
every job page. Built entirely from real markup pulled live, not
assumed from convention:

- Title/company: the <title> tag is "{Job Title} at {Company} |  MyJobMag"
  (confirmed exact spacing with double space before "MyJobMag") -- more
  reliable than the on-page <h1>, which is plain unstructured text.
- Key facts (type, qualification, experience, location, field): a clean
  repeated <li><span class="jkey-title">...</span> <span class="jkey-info">
  ...</span></li> pattern inside <ul class="job-key-info">.
- Description: the <div class="job-details"> block -- confirmed it
  contains only <p>/<ul>/<li> tags, no nested <div>, up to the next
  sibling ad-container div, so a non-greedy match up to that next <div>
  is safe.
- Posted date: <div id="posted-date"><b>Posted:</b> {date}</div>.
- Listing pages: /jobs, paginated as /jobs/page/{n} (path-based, NOT a
  ?page= query param -- different from BrighterMonday, confirmed live).
  Each listing links to /job/{slug} (relative).

Bulk polling reuses extract_from_url() per job, same pattern as
BrighterMonday.

As of 2026-07-30, also crawls 45 of MyJobMag's own "field" category
pages (see CATEGORY_SLUGS) alongside the general /jobs feed -- not just
medical. Same reasoning as BrighterMonday's equivalent expansion: the
general feed under-represents any category that isn't currently
trending, and that gap applies to every profession, not just nursing.
Confirmed live this category style paginates as /jobs-by-field/{slug}/
{n} (direct number, no "page" segment) -- different from the general
feed's /jobs/page/{n} -- so LISTING_SOURCES carries a page_style per
source rather than assuming one URL-building rule fits every source.
"""

import html
import logging
import re
import time

import httpx

from eliteprocareers.jobs.connectors.base import (
    ConnectorCapabilities,
    JobConnector,
    SupportTier,
)
from eliteprocareers.jobs.connectors.registry import registry

BASE_URL = "https://www.myjobmag.co.ke"

TITLE_TAG_PATTERN = re.compile(r"<title>(.*?)\s*\|\s*MyJobMag</title>", re.DOTALL)
COMPANY_LINK_PATTERN = re.compile(r"View Jobs at ([^<]+)</a>")
KEY_INFO_PATTERN = re.compile(
    r'<span class="jkey-title">([^<]+)</span>\s*<span class="jkey-info">(.*?)</span>',
    re.DOTALL,
)
POSTED_DATE_PATTERN = re.compile(
    r'id="posted-date"><b[^>]*>Posted:</b>\s*([^<]+)</div>'
)
DESCRIPTION_PATTERN = re.compile(
    r'<div class="job-details">(.*?)</div>\s*<div class="mag-b bm-t-20',
    re.DOTALL,
)
LISTING_URL_PATTERN = re.compile(r'href="(/job/[a-z0-9-]+)"')

logger = logging.getLogger(__name__)

# Fallback for listings with no "View Jobs at {Company}" link (confirmed
# live 2026-07-19 on "Transport Manager at Karmec Company Ltd" -- link is
# absent on some listings even though the company is real and present in
# the page's <h1>, e.g. "{Title} at {Company}" inside <ul class="read-h1">.
# Confirmed this h1 format is consistent by cross-checking against a known
# -working listing ("Zonal Sales Manager - Mombasa CBD at HCS Affiliates
# Group"). Use rsplit on the LAST " at " to avoid mis-splitting a title
# that itself contains " at " (e.g. "Manager at Large Accounts").
H1_TITLE_COMPANY_PATTERN = re.compile(
    r'<ul class="read-h1">.*?<h1>\s*(.*?)\s*</h1>', re.DOTALL
)


def _strip_tags(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


@registry.register
class MyJobMagConnector(JobConnector):
    source_name = "myjobmag"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(
        scheduled_polling=True,
        url_import=True,
        full_job_details=True,
    )
    notes = (
        "No JSON-LD (confirmed live 2026-07-19, unlike BrighterMonday) -- "
        "parses a consistent HTML template instead: <title> tag for "
        "title/company (format '{title} at {company} |  MyJobMag'), "
        "<ul class=\"job-key-info\"> for type/qualification/experience/"
        "location/field, <div class=\"job-details\"> for the description "
        "body. More fragile than JSON-LD-based connectors since it "
        "depends on the site's current template rather than intentionally "
        "published structured data -- re-verify this parser if MyJobMag "
        "redesigns their job pages. Listing pages paginate as "
        "/jobs/page/{n} (path-based, confirmed different from "
        "BrighterMonday's ?page= query param)."
    )

    BASE_LISTING_URL = f"{BASE_URL}/jobs"

    # Confirmed live 2026-07-30 by fetching /jobs-by-field directly and
    # reading its own field list. MyJobMag's raw list has 51 entries;
    # excluded 6 that aren't real professional categories (they're
    # meta-filters or non-employment): "Bursary and Scholarships",
    # "General", "Graduate Jobs", "Internships", "RFP / RFQ / EOI",
    # "Volunteer". The remaining 45 are genuine fields. Spot-checked 2
    # of the 45 individually (medical, sales-marketing -- one small
    # category, one of the largest) to confirm both the direct /{n}
    # pagination shape and the /job/{slug} URL shape hold beyond just
    # the medical category added earlier -- not assumed to hold for all
    # 45 just because 2 matched, but same site engine/template
    # throughout made that a reasonable inference to build on.
    CATEGORY_SLUGS: list[str] = [
        "administration",
        "agriculture",
        "art",
        "aviation",
        "banking",
        "caregiver-nanny-social-workers",
        "catering",
        "building-and-construction",
        "consultancy",
        "content-editorial",
        "customer-care",
        "research-data-analysis",
        "travel-and-logistics",
        "education",
        "engineering",
        "safety-and-environment-hse",
        "accounting-audit",
        "hospitality",
        "human-resources",
        "information-technology",
        "insurance",
        "janitorial-services",
        "legal",
        "logistics",
        "manufacturing",
        "marketing-communication",
        "media",
        "medical",
        "ngo",
        "oil-refining-and-marketing",
        "pharmaceutical",
        "procurement-store-keeping",
        "product-management",
        "project-management",
        "real-estate",
        "research",
        "risk-compliance",
        "sales-marketing",
        "science",
        "security",
        "maritime",
        "sports-personal-care",
        "strategic-top-management",
        "travels-amp-tours",
        "ux-design-architecture",
    ]

    LISTING_SOURCES: list[tuple[str, str]] = [(BASE_LISTING_URL, "page")] + [
        (f"{BASE_URL}/jobs-by-field/{slug}", "direct") for slug in CATEGORY_SLUGS
    ]

    # See BrighterMondayConnector.CATEGORY_MAX_PAGES for the full
    # reasoning -- same bounded-volume tradeoff, applied here too now
    # that this connector also crawls 45 category sources.
    CATEGORY_MAX_PAGES = 3

    # See BrighterMondayConnector.REQUEST_DELAY_SECONDS.
    REQUEST_DELAY_SECONDS = 0.2

    @staticmethod
    def _page_url(base_url: str, page_style: str, page_num: int) -> str:
        if page_num == 1:
            return base_url
        if page_style == "page":
            return f"{base_url}/page/{page_num}"
        return f"{base_url}/{page_num}"

    def extract_from_url(self, url: str) -> dict | None:
        """Fetch a single MyJobMag job listing page and parse it into a
        dict shaped to match the `jobs` table columns.

        Returns None on any parsing failure below, OR if the request
        itself fails (timeout, connection error, non-2xx status) -- added
        2026-07-30 after this exact call raised httpx.ReadTimeout mid-run
        against a real MyJobMag job page and crashed the entire ingestion
        run, losing every job already fetched from all 46 sources crawled
        before it (nothing is saved until fetch_jobs returns as a whole).
        One bad page out of hundreds shouldn't cost the whole run.
        """
        try:
            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        text = response.text

        title_match = TITLE_TAG_PATTERN.search(text)
        if not title_match:
            return None
        title_line = html.unescape(title_match.group(1)).strip()
        title = title_line.split(" at ", 1)[0] if " at " in title_line else title_line

        # Confirmed live: the <title> tag sometimes appends a trailing
        # "Month, Year" after the company name (e.g. "... at Kenya Power
        # June, 2026 |  MyJobMag"), which a plain " at " split would
        # wrongly fold into the company name. The "View Jobs at {Company}"
        # link elsewhere on the page is unambiguous and doesn\'t have
        # this quirk, so use that instead.
        company_match = COMPANY_LINK_PATTERN.search(text)
        company = html.unescape(company_match.group(1)).strip() if company_match else None

        # Confirmed live: some listings (e.g. "Transport Manager at Karmec
        # Company Ltd") have no "View Jobs at {Company}" link at all, even
        # though the company is real. Fall back to the page's <h1>, which
        # follows the same "{Title} at {Company}" format -- confirmed
        # against both the broken listing and a known-working one.
        if company is None:
            h1_match = H1_TITLE_COMPANY_PATTERN.search(text)
            if h1_match:
                h1_text = html.unescape(h1_match.group(1)).strip()
                if " at " in h1_text:
                    company = h1_text.rsplit(" at ", 1)[1].strip()

        key_info = {
            _strip_tags(k): _strip_tags(v)
            for k, v in KEY_INFO_PATTERN.findall(text)
        }
        location = key_info.get("Location")

        posted_match = POSTED_DATE_PATTERN.search(text)
        posted_at = posted_match.group(1).strip() if posted_match else None

        desc_match = DESCRIPTION_PATTERN.search(text)
        description = desc_match.group(1).strip() if desc_match else None

        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        return {
            "source": self.source_name,
            "external_id": external_id,
            "company": company,
            "title": title,
            "description": description,
            "url": url,
            "location": location,
            "posted_at": posted_at,
            "raw_json": key_info,
        }

    def fetch_jobs(self, max_pages: int = 5, **kwargs) -> list[dict]:
        """Crawl every configured listing source (LISTING_SOURCES). The
        general feed (BASE_LISTING_URL) is capped at max_pages (default
        5, still caller-overridable, unchanged from before this
        expansion); every category source is capped at the smaller,
        fixed CATEGORY_MAX_PAGES instead. Same per-source-pagination-
        stop / cross-source-dedup / politeness-delay reasoning as
        BrighterMondayConnector.fetch_jobs -- see that docstring for the
        full explanation.
        """
        jobs: list[dict] = []
        extracted_urls: set[str] = set()

        for source_index, (base_url, page_style) in enumerate(self.LISTING_SOURCES, start=1):
            source_seen: set[str] = set()
            source_max_pages = max_pages if base_url == self.BASE_LISTING_URL else self.CATEGORY_MAX_PAGES
            logger.info(
                "MyJobMag source %d/%d: %s (max_pages=%d)",
                source_index, len(self.LISTING_SOURCES), base_url, source_max_pages,
            )

            for page_num in range(1, source_max_pages + 1):
                page_url = self._page_url(base_url, page_style, page_num)
                time.sleep(self.REQUEST_DELAY_SECONDS)
                try:
                    response = httpx.get(page_url, timeout=15.0, follow_redirects=True)
                except httpx.HTTPError:
                    break
                if response.status_code != 200:
                    break

                hrefs = set(LISTING_URL_PATTERN.findall(response.text))
                if not hrefs:
                    break
                full_urls = {BASE_URL + h for h in hrefs}

                new_to_source = full_urls - source_seen
                if not new_to_source:
                    break
                source_seen |= new_to_source

                for listing_url in new_to_source:
                    if listing_url in extracted_urls:
                        continue
                    extracted_urls.add(listing_url)
                    time.sleep(self.REQUEST_DELAY_SECONDS)
                    job = self.extract_from_url(listing_url)
                    if job is not None:
                        jobs.append(job)

        return jobs
