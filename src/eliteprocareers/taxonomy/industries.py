"""
Canonical industry/function taxonomy -- the ONE vocabulary that both
sides of matching operate on: job connectors normalize their
source-specific categories into this list via attribute_extraction.py,
and CVTrack.industries is migrated onto this same list (see
scripts/migrate_track_industries.py). check_industry in filtering.py
never sees a raw source string on either side.

Deliberately generic, not tied to any one job board's category names --
built to also cover Gulf-market boards (Bayt, GulfTalent, NaukriGulf)
later without rework, per the Kenya-first/Gulf-second/global roadmap.

Blends two real classification axes into one flat list ON PURPOSE:
sector (what industry the employer is in, e.g. "Healthcare") and
function (what role type, e.g. "Sales") are genuinely different axes,
but candidate tracks are named by BOTH kinds interchangeably in
practice (e.g. "Supply Chain / Procurement" is a function, "the
healthcare industry" is a sector) -- so a single flat list is what's
actually useful for matching a candidate's stated target against a
job's tags, not a purity exercise in taxonomy design.

HOW TO EXTEND:
1. Add the new canonical value to CANONICAL_INDUSTRIES.
2. Add an entry to the relevant SOURCE_..._MAP for whatever raw value
   needs to map to it. A raw value can map to a single canonical
   string, a list of canonical strings (if the raw value genuinely
   spans more than one canonical category), or None (explicitly
   excluded, e.g. "Unspecified" sentinels -- not just left unmapped).
3. Run scripts/backfill_*_attributes.py in dry-run mode -- unmapped
   raw values are reported explicitly, never silently dropped, so a
   new source value you haven't seen yet gets surfaced instead of
   disappearing into an empty attributes["industry"].

A module-level self-check runs at import time (bottom of this file)
asserting every mapped value is actually in CANONICAL_INDUSTRIES --
catches a typo in a mapping table immediately rather than at runtime
in production.
"""

CANONICAL_INDUSTRIES = frozenset(
    {
        # --- Sector (what industry the employer operates in) ---
        "Healthcare",
        "Banking & Insurance",
        "Construction",
        "Education",
        "Energy & Utilities",
        "Manufacturing",
        "Real Estate",
        "Retail & FMCG",
        "Tourism & Travel",
        "Agriculture",
        "Hospitality",
        "Health, Wellness & Fitness",
        "IT & Telecoms",
        "Media & Advertising",
        "Entertainment & Events",
        "Oil & Gas",
        "Government & Public Sector",
        "NGO & Nonprofit",
        "Automotive",
        # --- Function (role type, cross-industry) ---
        "Sales",
        "Accounting & Finance",
        "Marketing & Communications",
        "Customer Service",
        "Human Resources & Recruitment",
        "Supply Chain & Procurement",
        "Logistics & Transport",
        "Engineering & Technology",
        "Software & Data",
        "Product & Project Management",
        "Administration",
        "Legal",
        "Management & Business Development",
        "Creative & Design",
        "Quality Control & Assurance",
        "Health & Safety",
        "Medical & Pharmaceutical",
        "Trades & Services",
        "Security & Safety",
        "Science & Research",
        "Media, Content & Journalism",
    }
)


# --- BrighterMonday: schema.org JobPosting.industry -> canonical ---
# Confirmed live 2026-07-19 against all 80 ingested jobs -- 17 distinct
# raw values including the "Unspecified" sentinel (16 jobs).
SOURCE_BRIGHTERMONDAY_INDUSTRY_MAP: dict[str, str | list[str] | None] = {
    "Advertising, Media & Communications": "Media & Advertising",
    "Agriculture, Fishing & Forestry": "Agriculture",
    "Banking, Finance & Insurance": "Banking & Insurance",
    "Construction": "Construction",
    "Education": "Education",
    "Energy & Utilities": "Energy & Utilities",
    "Entertainment, Events & Sport": "Entertainment & Events",
    "Healthcare": "Healthcare",
    "Hospitality & Hotel": "Hospitality",
    "IT & Telecoms": "IT & Telecoms",
    "Manufacturing & Warehousing": "Manufacturing",
    "Real Estate": "Real Estate",
    "Recruitment": "Human Resources & Recruitment",
    "Retail, Fashion & FMCG": "Retail & FMCG",
    "Shipping & Logistics": "Logistics & Transport",
    "Tourism & Travel": "Tourism & Travel",
    "Unspecified": None,  # explicit sentinel, not a real value -- excluded, not unmapped
    # Added 2026-08-05 (v40) -- discovered live against the full 1,009-job
    # BrighterMonday corpus (grown from 80 jobs since this table was last
    # confirmed 2026-07-19). These 5 values had zero occurrences in the
    # original sample and were silently landing every job that carried
    # them in `unmapped`, i.e. attributes["industry"] never got set for
    # them. Mappings below are a reasonable first pass, NOT independently
    # confirmed the way the original 16 were -- flag for review like
    # _INDUSTRY_MISMATCH_PENALTY's 0.3 multiplier.
    "NGO, NPO & Charity": "NGO & Nonprofit",
    "Automotive & Aviation": ["Automotive", "Engineering & Technology"],
    "Enforcement & Security": "Security & Safety",
    "Law & Compliance": "Legal",
    "Government": "Government & Public Sector",
}

# --- BrighterMonday: schema.org JobPosting.occupationalCategory -> canonical ---
# Confirmed live 2026-07-19 against all 80 ingested jobs -- 21 distinct
# raw values including "Unspecified" (4 jobs).
SOURCE_BRIGHTERMONDAY_OCCUPATIONAL_CATEGORY_MAP: dict[str, str | list[str] | None] = {
    "Accounting, Auditing & Finance": "Accounting & Finance",
    "Admin & Office": "Administration",
    "Creative & Design": "Creative & Design",
    "Customer Service & Support": "Customer Service",
    "Driver & Transport Services": "Logistics & Transport",
    "Engineering & Technology": "Engineering & Technology",
    "Farming & Agriculture": "Agriculture",
    "Health & Safety": "Health & Safety",
    "Hospitality & Leisure": "Hospitality",
    "Human Resources": "Human Resources & Recruitment",
    "Legal Services": "Legal",
    "Management & Business Development": "Management & Business Development",
    "Marketing & Communications": "Marketing & Communications",
    "Medical & Pharmaceutical": "Medical & Pharmaceutical",
    "Product & Project Management": "Product & Project Management",
    "Quality Control & Assurance": "Quality Control & Assurance",
    "Sales": "Sales",
    "Software & Data": "Software & Data",
    "Supply Chain & Procurement": "Supply Chain & Procurement",
    "Trades & Services": "Trades & Services",
    "Unspecified": None,
    # Added 2026-08-05 (v40) -- same staleness issue as
    # SOURCE_BRIGHTERMONDAY_INDUSTRY_MAP above, confirmed live against the
    # same grown corpus. Same caveat: reasonable first pass, not yet
    # independently confirmed.
    "Research, Teaching & Training": ["Education", "Science & Research"],
    "Food Services & Catering": "Hospitality",
    "Building & Architecture": ["Construction", "Creative & Design"],
    "Estate Agents & Property Management": "Real Estate",
    "Consulting & Strategy": "Management & Business Development",
    "Community & Social Services": "NGO & Nonprofit",
}

# --- MyJobMag: raw_json["Job Field"] (post-split, see attribute_extraction
# ._extract_categories()'s \xa0-based splitter) -> canonical ---
# Covers every value seen in the 246 ingested jobs as of 2026-07-19 --
# NOT guaranteed exhaustive (only the top 30 by frequency were pulled
# live; long-tail single-occurrence values may exist). Any raw value
# not in this dict is reported as UNMAPPED by the backfill script's
# dry run, never silently dropped -- see normalize_categories() below.
SOURCE_MYJOBMAG_JOB_FIELD_MAP: dict[str, str | list[str] | None] = {
    "Food, Beverage and Hospitality": "Hospitality",
    "Sales and Business Development": ["Sales", "Management & Business Development"],
    "Finance / Accounting / Audit": "Accounting & Finance",
    "Engineering / Technical": "Engineering & Technology",
    "Catering / Confectionery": "Hospitality",
    "Medical / Healthcare": "Healthcare",
    "Administration / Facilities": "Administration",
    "Marketing and Communication": "Marketing & Communications",
    "Customer Care, Success and Service": "Customer Service",
    "Human Resources / HR": "Human Resources & Recruitment",
    "Procurement / Store-keeping / Supply Chain": "Supply Chain & Procurement",
    "Banking": "Banking & Insurance",
    "Data, Business Analysis and AI": "Software & Data",
    "ICT / Computer": "IT & Telecoms",
    "Project and Program Management": "Product & Project Management",
    "Security / Intelligence": "Security & Safety",
    "Logistics": "Logistics & Transport",
    "Education / Teaching / Training": "Education",
    "Content, Editorial and Journalism": "Media, Content & Journalism",
    "Art / Crafts / Languages": "Creative & Design",
    "Manufacturing": "Manufacturing",
    "Agriculture / Agro-Allied": "Agriculture",
    "Science": "Science & Research",
    "Driving": "Trades & Services",
    "Pharmaceutical": "Medical & Pharmaceutical",
    "Environment Health and Safety": "Health & Safety",
    # Not a field/sector -- it's a program type, already captured via
    # attributes["employment_type"] == "internship". Explicitly
    # excluded rather than invented as a fake category.
    "Internships": None,
    # Added 2026-07-20 after review of live UNMAPPED report from the
    # MyJobMag backfill dry run (12 categories, 20 jobs total):
    "Media Production and Entertainment": ["Media, Content & Journalism", "Entertainment & Events"],
    "Graduate Jobs": None,  # program type, not an industry -- same treatment as Internships
    "Insurance": "Banking & Insurance",
    "Consultancy": "Management & Business Development",
    "Aviation / Aerospace": ["Engineering & Technology", "Logistics & Transport"],
    "Product Management": "Product & Project Management",
    "Legal and Regulatory": "Legal",
    "Janitorial Services": "Trades & Services",
    "Shipping and Maritime": ["Logistics & Transport", "Supply Chain & Procurement"],
    "NGO/Non-Profit": "NGO & Nonprofit",
    "UX, Design and Architecture": "Creative & Design",
    "Sports, Fitness and Personal Care": "Health, Wellness & Fitness",
    # Added 2026-08-05 (v40) -- discovered live against the full
    # 2,363-job MyJobMag corpus (grown from 246 jobs since this table
    # was last confirmed 2026-07-19/20; the 45-category expansion this
    # covers happened 2026-07-30, after the last confirmation date).
    # Same caveat as the two BrighterMonday additions above: reasonable
    # first pass, not yet independently confirmed. "Caregiver / Nanny /
    # Social Workers" is deliberately NOT mapped to "Healthcare" --
    # domestic/personal care is a different category from clinical
    # nursing, and conflating them would reintroduce exactly the kind
    # of false positive this session's investigation was chasing.
    "Construction and Site Engineering": ["Construction", "Engineering & Technology"],
    "Real Estate": "Real Estate",
    "Risk Management and Compliance": ["Legal", "Accounting & Finance"],
    "Research and Development": "Science & Research",
    "Oil and Gas, Energy and Mining": ["Oil & Gas", "Energy & Utilities"],
    "Travels and Tours": "Tourism & Travel",
    "Strategic and Top Management": "Management & Business Development",
    "Bursary and Scholarships": "Education",
    "Caregiver / Nanny / Social Workers": "Health, Wellness & Fitness",
    "Volunteer": None,  # program type, not an industry -- same treatment as Internships
    "RFP / RFQ / EOI": "Supply Chain & Procurement",
}

# --- CVTrack.track_name -> canonical categories ---
# A track can map to MULTIPLE canonical categories (OR-match semantics
# in check_industry -- a job passes if ANY category overlaps), so a
# candidate doesn't miss real opportunities just because an employer
# classified a job differently than the candidate phrased their track.
# Confirmed with the user 2026-07-19 for the two tracks that exist
# today; extend this dict as new track names are created.
CV_TRACK_NAME_MAP: dict[str, list[str]] = {
    "Product Management / SaaS": ["Product & Project Management", "Software & Data"],
    "Supply Chain / Procurement": ["Supply Chain & Procurement", "Logistics & Transport"],
}


_UNMAPPED = object()  # sentinel distinguishing "not in map" from "mapped to None"


def normalize_categories(
    raw_values: list[str], mapping: dict[str, str | list[str] | None]
) -> tuple[list[str], list[str]]:
    """Maps a list of raw source-specific category strings through the
    given mapping table into a deduplicated list of canonical values.

    Returns (canonical, unmapped) -- unmapped is every raw value that
    wasn't a key in `mapping` at all (as opposed to a raw value that
    WAS in the mapping but explicitly maps to None, e.g. "Unspecified"
    or "Internships" -- those are intentional exclusions, not gaps).
    Callers (backfill scripts) surface `unmapped` so a genuinely new
    raw value from a source gets reviewed and added to the mapping
    table, rather than silently vanishing from attributes["industry"].
    """
    canonical: list[str] = []
    unmapped: list[str] = []

    for raw in raw_values:
        mapped = mapping.get(raw, _UNMAPPED)
        if mapped is _UNMAPPED:
            unmapped.append(raw)
            continue
        if mapped is None:
            continue
        if isinstance(mapped, list):
            canonical.extend(mapped)
        else:
            canonical.append(mapped)

    # dedupe, preserving first-seen order
    seen: set[str] = set()
    deduped: list[str] = []
    for c in canonical:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    return deduped, unmapped


def _self_check() -> None:
    """Runs at import time -- asserts every mapped value across every
    table is actually in CANONICAL_INDUSTRIES, so a typo in a mapping
    table fails immediately at import rather than silently producing
    an attributes["industry"] value that can never match anything.
    """
    all_maps = (
        SOURCE_BRIGHTERMONDAY_INDUSTRY_MAP,
        SOURCE_BRIGHTERMONDAY_OCCUPATIONAL_CATEGORY_MAP,
        SOURCE_MYJOBMAG_JOB_FIELD_MAP,
    )
    for source_map in all_maps:
        for raw, mapped in source_map.items():
            if mapped is None:
                continue
            values = mapped if isinstance(mapped, list) else [mapped]
            for value in values:
                assert value in CANONICAL_INDUSTRIES, (
                    f"Mapping table entry {raw!r} -> {value!r} is not in "
                    f"CANONICAL_INDUSTRIES -- typo or missing addition to "
                    f"the canonical list."
                )

    for track_name, values in CV_TRACK_NAME_MAP.items():
        for value in values:
            assert value in CANONICAL_INDUSTRIES, (
                f"CV_TRACK_NAME_MAP entry {track_name!r} -> {value!r} is not "
                f"in CANONICAL_INDUSTRIES -- typo or missing addition."
            )


_self_check()
