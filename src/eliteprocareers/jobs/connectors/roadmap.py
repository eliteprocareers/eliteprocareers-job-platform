"""
Documented roadmap entries — sources we've evaluated but not yet built.

These are real registry entries, not comments, specifically so the tier
and reasoning are queryable (registry.by_tier(...)) and won't get lost
between sessions. None of these implement fetch_jobs() or
extract_from_url() yet — that's the point. When one becomes buildable,
change its class attributes and implement the method; nothing else in
the ingestion engine changes.
"""

from eliteprocareers.jobs.connectors.base import (
    ConnectorCapabilities,
    JobConnector,
    SupportTier,
)
from eliteprocareers.jobs.connectors.registry import registry


# ---- FULLY_SUPPORTED, not yet built (confirmed feasible, next in line) ----

@registry.register
class LeverConnector(JobConnector):
    source_name = "lever"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(scheduled_polling=True, full_job_details=True)
    notes = (
        "Public JSON API, no auth: api.lever.co/v0/postings/{company}?mode=json. "
        "Confirmed via third-party ATS comparison research 2026-07-19. "
        "Not yet implemented — next connector after Greenhouse."
    )


@registry.register
class AshbyConnector(JobConnector):
    source_name = "ashby"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(scheduled_polling=True, full_job_details=True)
    notes = (
        "Official documented public API: "
        "api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true. "
        "Confirmed via developers.ashbyhq.com docs 2026-07-19. Not yet implemented."
    )


@registry.register
class SmartRecruitersConnector(JobConnector):
    source_name = "smartrecruiters"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(scheduled_polling=True, full_job_details=True)
    notes = (
        "Public JSON API, no auth, paginated (limit/offset): "
        "api.smartrecruiters.com/v1/companies/{company}/postings. "
        "Confirmed 2026-07-19. Not yet implemented."
    )


@registry.register
class RecruiteeConnector(JobConnector):
    source_name = "recruitee"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(scheduled_polling=True, full_job_details=True)
    notes = (
        "Public JSON API, no auth: {company}.recruitee.com/api/offers/. "
        "Confirmed 2026-07-19. Not yet implemented."
    )


@registry.register
class BrighterMondayConnector(JobConnector):
    source_name = "brightermonday"
    support_tier = SupportTier.FULLY_SUPPORTED
    capabilities = ConnectorCapabilities(scheduled_polling=True, full_job_details=True)
    notes = (
        "Job detail pages embed Schema.org JobPosting JSON-LD — structured "
        "data intentionally published for Google for Jobs indexing, not "
        "reverse-engineered. Most Kenya-relevant source identified so far. "
        "Confirmed 2026-07-19. Not yet implemented — high priority, and its "
        "JSON-LD parser is the same code url_import.py will reuse."
    )


# ---- USER_ASSISTED — single-URL, user-initiated only, no bulk access ----

@registry.register
class LinkedInConnector(JobConnector):
    source_name = "linkedin"
    support_tier = SupportTier.USER_ASSISTED
    capabilities = ConnectorCapabilities(url_import=True, user_assisted_application=True)
    notes = (
        "Actively blocks automated bulk access — project principle "
        "explicitly excludes building anti-bot bypass for this platform. "
        "Individual job posting pages MAY carry JobPosting JSON-LD (used "
        "for Google for Jobs indexing) — untested whether this still works "
        "without login, and whether it survives even a single fetch given "
        "LinkedIn's bot detection. To re-evaluate: test extract_from_url() "
        "against one real LinkedIn job URL, single request, once "
        "url_import.py exists. If it works, stays single-URL/user-initiated "
        "only — never looped or scheduled."
    )


@registry.register
class IndeedConnector(JobConnector):
    source_name = "indeed"
    support_tier = SupportTier.USER_ASSISTED
    capabilities = ConnectorCapabilities(url_import=True, user_assisted_application=True)
    notes = "Same reasoning and same re-evaluation plan as LinkedInConnector."


@registry.register
class BaytConnector(JobConnector):
    source_name = "bayt"
    support_tier = SupportTier.USER_ASSISTED
    capabilities = ConnectorCapabilities(url_import=True)
    notes = (
        "No public API or feed found. Every third-party integration "
        "discovered uses paid scraping with residential proxies "
        "specifically to avoid getting blocked — functionally the same "
        "category as bypassing LinkedIn/Indeed's protections, so no "
        "dedicated connector is being built. A user-pasted individual job "
        "URL may still work via url_import.py's generic JSON-LD extractor, "
        "same untested/re-evaluate-later status as LinkedIn."
    )


@registry.register
class NaukriGulfConnector(JobConnector):
    source_name = "naukrigulf"
    support_tier = SupportTier.USER_ASSISTED
    capabilities = ConnectorCapabilities(url_import=True)
    notes = "Same reasoning as BaytConnector."


@registry.register
class GulfTalentConnector(JobConnector):
    source_name = "gulftalent"
    support_tier = SupportTier.USER_ASSISTED
    capabilities = ConnectorCapabilities(url_import=True)
    notes = "Same reasoning as BaytConnector."


# ---- UNDER_RESEARCH — no maintainable path identified yet ----

@registry.register
class WorkdayConnector(JobConnector):
    source_name = "workday"
    support_tier = SupportTier.UNDER_RESEARCH
    capabilities = ConnectorCapabilities()
    notes = (
        "No documented public API. Workday-hosted career sites call an "
        "internal JSON endpoint (myworkdayjobs.com/wday/cxs/...) that their "
        "own frontend uses but isn't published for third-party consumption "
        "— different category from Greenhouse/Ashby/etc., which explicitly "
        "publish their feeds. Relying on it means depending on an "
        "undocumented internal API that could change or block us without "
        "notice. Re-evaluate if Workday ever publishes something official, "
        "or if this becomes high-value enough to accept that risk deliberately."
    )


@registry.register
class BambooHRConnector(JobConnector):
    source_name = "bamboohr"
    support_tier = SupportTier.UNDER_RESEARCH
    capabilities = ConnectorCapabilities()
    notes = (
        "Requires a per-tenant auth token — no genuine public unauthenticated "
        "feed exists. Would need each employer's individual cooperation, "
        "which doesn't fit a broad-ingestion model. Re-evaluate only if a "
        "specific target employer on BambooHR is worth requesting API access from."
    )


@registry.register
class MyJobMagConnector(JobConnector):
    source_name = "myjobmag"
    support_tier = SupportTier.UNDER_RESEARCH
    capabilities = ConnectorCapabilities()
    notes = (
        "No structured data (no JSON-LD, unlike BrighterMonday) — would "
        "require raw HTML scraping with CSS selectors, fragile against page "
        "redesigns. Worth checking their terms of service before building "
        "even a basic scraper. Re-evaluate after BrighterMonday connector "
        "proves out the value of Kenya-specific sourcing."
    )


@registry.register
class TeamtailorConnector(JobConnector):
    source_name = "teamtailor"
    support_tier = SupportTier.UNDER_RESEARCH
    capabilities = ConnectorCapabilities()
    notes = (
        "Not yet researched — unlike the other ATSs above, its public API "
        "availability wasn't confirmed either way. Re-evaluate before "
        "building, don't assume either a working API or its absence."
    )
