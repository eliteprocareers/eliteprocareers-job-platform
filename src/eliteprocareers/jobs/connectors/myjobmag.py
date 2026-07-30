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

As of 2026-07-30, also crawls /jobs-by-field/medical alongside the
general /jobs feed (see LISTING_SOURCES) -- same reasoning as
BrighterMonday's medical-pharmaceutical addition. Confirmed live this
category paginates as /jobs-by-field/medical/{n} (direct number, no
"page" segment), a different shape from the general feed's
/jobs/page/{n} -- not assumed to match.
"""

import html
import re

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

    # Crawled in addition to the general feed, same reasoning as the
    # BrighterMonday connector's LISTING_SOURCES (added 2026-07-30): the
    # general feed under-represents any category that isn't currently
    # trending in postings. Confirmed live 2026-07-30 that
    # /jobs-by-field/medical uses a DIFFERENT pagination shape from the
    # general feed -- direct /{n} (e.g. /jobs-by-field/medical/2), not
    # /page/{n} -- so each source carries its own page_style rather than
    # assuming one URL-building rule fits every source.
    LISTING_SOURCES: list[tuple[str, str]] = [
        (BASE_LISTING_URL, "page"),
        (f"{BASE_URL}/jobs-by-field/medical", "direct"),
    ]

    @staticmethod
    def _page_url(base_url: str, page_style: str, page_num: int) -> str:
        if page_num == 1:
            return base_url
        if page_style == "page":
            return f"{base_url}/page/{page_num}"
        return f"{base_url}/{page_num}"

    def extract_from_url(self, url: str) -> dict | None:
        response = httpx.get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
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
        """Crawl every configured listing source (LISTING_SOURCES) up to
        max_pages each. Same per-source-pagination-stop / cross-source-
        dedup reasoning as BrighterMondayConnector.fetch_jobs -- see that
        docstring for the full explanation.
        """
        jobs: list[dict] = []
        extracted_urls: set[str] = set()

        for base_url, page_style in self.LISTING_SOURCES:
            source_seen: set[str] = set()

            for page_num in range(1, max_pages + 1):
                page_url = self._page_url(base_url, page_style, page_num)
                response = httpx.get(page_url, timeout=15.0, follow_redirects=True)
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
                    job = self.extract_from_url(listing_url)
                    if job is not None:
                        jobs.append(job)

        return jobs
