"""
Greenhouse Job Board API fetcher.

No auth required — Job Board data is public. Endpoint:
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

Note: the API does not return company name per-job (only board-level),
so company_name is passed in by the caller rather than parsed from the response.
"""

import httpx

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


def fetch_greenhouse_jobs(board_token: str, company_name: str) -> list[dict]:
    """Fetch all published jobs for a Greenhouse board token.

    Returns a list of dicts shaped to match the `jobs` table columns,
    ready to pass to JobRepository.bulk_create() (after external_id dedup
    filtering by the caller).
    """
    url = f"{BASE_URL}/{board_token}/jobs"
    response = httpx.get(url, params={"content": "true"}, timeout=15.0)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data.get("jobs", []):
        location = job.get("location") or {}
        jobs.append({
            "source": "greenhouse",
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
