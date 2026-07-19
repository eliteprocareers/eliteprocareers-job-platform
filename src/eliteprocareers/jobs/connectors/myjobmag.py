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
        jobs: list[dict] = []
        seen_urls: set[str] = set()

        for page_num in range(1, max_pages + 1):
            page_url = (
                self.BASE_LISTING_URL
                if page_num == 1
                else f"{self.BASE_LISTING_URL}/page/{page_num}"
            )
            response = httpx.get(page_url, timeout=15.0, follow_redirects=True)
            if response.status_code != 200:
                break

            hrefs = set(LISTING_URL_PATTERN.findall(response.text))
            full_urls = {BASE_URL + h for h in hrefs}
            new_urls = full_urls - seen_urls
            if not new_urls:
                break
            seen_urls |= new_urls

            for listing_url in new_urls:
                job = self.extract_from_url(listing_url)
                if job is not None:
                    jobs.append(job)

        return jobs
