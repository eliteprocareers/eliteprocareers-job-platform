"""
Core contract every job source implements — the Job Ingestion Engine's
connector interface.

Design principle: a connector declares its SupportTier and Capabilities.
The ingestion engine (and, later, the application workflow) reads those
flags to decide what to do with a source — it never hardcodes per-source
behavior. Moving a source between tiers, or turning on a capability once
it becomes feasible, means editing that one connector's class attributes —
nothing else in the system changes.
"""

from abc import ABC
from dataclasses import dataclass
from enum import Enum


class SupportTier(str, Enum):
    """Where a source currently stands — not a permanent judgment.

    FULLY_SUPPORTED: official API, documented public feed, or structured
        data (e.g. JSON-LD) the source intentionally publishes.
    USER_ASSISTED: no bulk/automated access, but a user can hand the
        system a specific URL and the system extracts what's legitimately
        there for that one page.
    UNDER_RESEARCH: no maintainable integration today. Stays in the
        registry with documented reasoning so it can be re-evaluated
        later, not silently dropped.
    """

    FULLY_SUPPORTED = "fully_supported"
    USER_ASSISTED = "user_assisted"
    UNDER_RESEARCH = "under_research"


@dataclass(frozen=True)
class ConnectorCapabilities:
    """What a connector can actually do. All default False — a connector
    only implements the methods its True capabilities promise.
    """

    scheduled_polling: bool = False       # fetch_jobs() — scheduled/batch ingestion
    url_import: bool = False              # extract_from_url() — single user-pasted URL
    full_job_details: bool = False        # returns full description, not just title/link
    company_discovery: bool = False       # can find companies on this source itself, vs. needing a curated list
    application_support: bool = False     # can assist with submitting an application at all
    automatic_application: bool = False   # can submit an application without a human step (NOT used — project principle requires human-in-the-loop; reserved for completeness, should stay False everywhere)
    user_assisted_application: bool = False  # prepares a complete draft for manual submission


class JobConnector(ABC):
    """Base contract. Subclasses set class-level source_name, support_tier,
    capabilities, and notes, and implement only the methods their
    capabilities actually promise.

    fetch_jobs() is only called by the ingestion engine if
    capabilities.scheduled_polling is True. extract_from_url() is only
    called if capabilities.url_import is True. A connector with neither
    capability (an UNDER_RESEARCH stub) implements nothing beyond the
    class attributes — it exists purely as a documented roadmap entry.
    """

    source_name: str
    support_tier: SupportTier
    capabilities: ConnectorCapabilities
    notes: str = ""

    def fetch_jobs(self, **kwargs) -> list[dict]:
        raise NotImplementedError(
            f"{self.source_name} does not implement scheduled polling."
        )

    def extract_from_url(self, url: str) -> dict | None:
        raise NotImplementedError(
            f"{self.source_name} does not implement URL import."
        )
