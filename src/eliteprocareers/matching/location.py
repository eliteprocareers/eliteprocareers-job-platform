"""
Location normalization — converts a job's location signal (structured
attributes and/or free-text display string) into a canonical
NormalizedLocation the scoring/filtering engine can compare against
candidate preferences, without ever doing string matching itself.

Roadmap note: the MVP is Kenya-first, then Gulf (UAE, Qatar, Saudi
Arabia, Kuwait, Oman, Bahrain), then global. This module stays fully
generic, but the curated city tables and test coverage are prioritized
for Kenyan and Gulf postings, since that's the MVP's real data.

Pipeline, tried in order (first hit wins):
  1. Connector-provided structured attributes (highest confidence) --
     jobs.attributes.country/state/city/remote, populated directly by a
     connector that extracted real structured data from its source.
  2. pycountry EXACT lookup (name / official name / ISO code) against
     tokens of the display text, plus US state-abbreviation handling
     for ambiguous 2-letter tokens.
  3. Project-specific aliases (UAE, KSA, UK, USA, ...) not covered by
     pycountry's own name variants.
  4. Curated city -> country tables for postings that give only a bare
     city name with no country (very common in Kenyan/Gulf postings).
     Kenya-first; extend with more markets as needed.
  5. Best-effort exact-country-name substring scan of the full text.
  6. Unknown -- returns None. Callers (the filtering engine) must treat
     this as "skip the location criterion", never as a non-match.

Deliberately NOT using pycountry's search_fuzzy() for country
resolution -- confirmed live it matches some Kenyan cities to "Kenya"
(Nairobi, Kisumu, Mombasa, Nyeri, Kakamega) but not others (Eldoret,
Thika fail outright with LookupError). That's coincidental string
similarity to country/subdivision names, not real city knowledge, and
silently guessing right some of the time on our top-priority market's
most common posting format is worse than skipping. Bare city names are
handled explicitly via CITY_COUNTRY_MAP instead (tier 4).

Known tradeoff: a bare 2-letter token (e.g. "CA") is treated as a US
state abbreviation before being tried as an ISO country code, since
"City, ST" is a very common US job-posting convention and a bare
country code in that position is rare. This means "Toronto, CA" would
be misread as California rather than Canada -- an acceptable tradeoff
for now since real postings for Canadian cities almost always use a
province code (e.g. "Toronto, ON") or spell out "Canada", not the
country's ISO code. Revisit if Canada becomes a priority market.
"""
import re

import pycountry
from pydantic import BaseModel

# Aliases pycountry doesn't resolve on its own. Gulf abbreviations
# (UAE, KSA) are here deliberately -- Gulf is the MVP's #2 priority
# market after Kenya. Matched case-insensitively as whole tokens, not
# substrings, to avoid false positives (e.g. "UK" should not match
# inside another word).
PROJECT_ALIASES: dict[str, str] = {
    "uae": "United Arab Emirates",
    "ksa": "Saudi Arabia",
    "uk": "United Kingdom",
    "usa": "United States",
    "us": "United States",
}

# Curated bare-city-name -> country lookup. Not exhaustive -- extend as
# real posting data surfaces cities we don't cover. Kenya-first per MVP
# priority; Gulf cities included since that's priority #2. Keys are
# matched case-insensitively as whole tokens.
CITY_COUNTRY_MAP: dict[str, str] = {
    # Kenya -- MVP priority 1. Major cities/towns seen in real job
    # postings, including ones pycountry's fuzzy matcher missed
    # (Eldoret, Thika) during testing.
    "nairobi": "Kenya",
    "mombasa": "Kenya",
    "kisumu": "Kenya",
    "nakuru": "Kenya",
    "eldoret": "Kenya",
    "thika": "Kenya",
    "malindi": "Kenya",
    "kitale": "Kenya",
    "garissa": "Kenya",
    "kakamega": "Kenya",
    "meru": "Kenya",
    "nyeri": "Kenya",
    "machakos": "Kenya",
    "kericho": "Kenya",
    "naivasha": "Kenya",
    "nanyuki": "Kenya",
    "kilifi": "Kenya",
    "kiambu": "Kenya",
    "ruiru": "Kenya",
    "voi": "Kenya",
    "isiolo": "Kenya",
    "kitui": "Kenya",
    "embu": "Kenya",
    "bungoma": "Kenya",
    "busia": "Kenya",
    "siaya": "Kenya",
    "narok": "Kenya",
    "kajiado": "Kenya",
    "lamu": "Kenya",
    # Gulf -- MVP priority 2.
    "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates",
    "sharjah": "United Arab Emirates",
    "riyadh": "Saudi Arabia",
    "jeddah": "Saudi Arabia",
    "dammam": "Saudi Arabia",
    "doha": "Qatar",
    "kuwait city": "Kuwait",
    "muscat": "Oman",
    "manama": "Bahrain",
}

REMOTE_KEYWORDS = ("remote", "work from home", "wfh")


class NormalizedLocation(BaseModel):
    """Canonical location shape used everywhere in scoring/filtering.
    raw_text is preserved for display -- never used for comparison.
    """
    country: str | None = None       # pycountry canonical name, e.g. "Kenya"
    country_code: str | None = None  # ISO 3166-1 alpha-2, e.g. "KE"
    state: str | None = None
    city: str | None = None
    remote: bool = False
    confidence: str | None = None    # 'structured' | 'pycountry' | 'alias' | 'city_table' | 'substring' | 'alias_substring' | None
    raw_text: str | None = None


def _lookup_country_exact(name: str):
    """Exact pycountry lookup only (name / official name / ISO code).
    Deliberately does NOT fall back to search_fuzzy() -- confirmed live
    that fuzzy matching produces coincidental, inconsistent hits on
    city names rather than real city knowledge. Returns a pycountry
    Country object or None -- never raises.
    """
    name = name.strip()
    if not name:
        return None
    try:
        return pycountry.countries.lookup(name)
    except LookupError:
        return None


def _lookup_us_subdivision(token: str):
    """Handle common 'City, ST' patterns (e.g. 'San Francisco, CA') via
    pycountry's US subdivisions. Returns (state_name, country) or None.
    """
    token = token.strip().upper()
    if len(token) != 2:
        return None
    try:
        subdivision = pycountry.subdivisions.get(code=f"US-{token}")
    except LookupError:
        return None
    if subdivision is None:
        return None
    return subdivision.name, pycountry.countries.get(alpha_2="US")


def normalize_location(
    location_text: str | None,
    attributes: dict | None = None,
) -> NormalizedLocation | None:
    attributes = attributes or {}
    is_remote_hint = bool(
        location_text and any(k in location_text.lower() for k in REMOTE_KEYWORDS)
    )

    # Tier 1: connector-provided structured attributes.
    if attributes.get("country") or attributes.get("remote") is not None:
        return NormalizedLocation(
            country=attributes.get("country"),
            country_code=attributes.get("country_code"),
            state=attributes.get("state"),
            city=attributes.get("city"),
            remote=bool(attributes.get("remote", is_remote_hint)),
            confidence="structured",
            raw_text=location_text,
        )

    if not location_text or not location_text.strip():
        return None

    tokens = [t.strip() for t in location_text.split(",") if t.strip()]

    # Tier 2: pycountry exact lookup on each token (handles "Kenya",
    # "Japan", full names, ISO codes), plus US state-abbreviation
    # handling for ambiguous 2-letter tokens (see module docstring for
    # the CA-vs-California-vs-Canada tradeoff).
    for token in reversed(tokens):  # country is usually the last segment
        if len(token) == 2:
            subdivision_result = _lookup_us_subdivision(token)
            if subdivision_result:
                state_name, country = subdivision_result
                city = tokens[0] if len(tokens) >= 2 else None
                return NormalizedLocation(
                    country=country.name,
                    country_code=country.alpha_2,
                    state=state_name,
                    city=city,
                    remote=is_remote_hint,
                    confidence="pycountry",
                    raw_text=location_text,
                )

        country = _lookup_country_exact(token)
        if country:
            state = tokens[-2] if len(tokens) >= 2 and tokens[-2] != token else None
            city = tokens[0] if len(tokens) >= 2 else None
            return NormalizedLocation(
                country=country.name,
                country_code=country.alpha_2,
                state=state,
                city=city,
                remote=is_remote_hint,
                confidence="pycountry",
                raw_text=location_text,
            )

    # Tier 3: project-specific aliases. Extracts city the same way
    # tier 2 does -- confirmed live this was silently dropped before
    # (e.g. "Dubai, UAE" lost city="Dubai" when it fell through to this
    # tier, since "UAE" isn't pycountry's official name/ISO code).
    for token in tokens:
        alias_target = PROJECT_ALIASES.get(token.strip().lower())
        if alias_target:
            country = _lookup_country_exact(alias_target)
            if country:
                other_tokens = [t for t in tokens if t != token]
                city = other_tokens[0] if other_tokens else None
                return NormalizedLocation(
                    country=country.name,
                    country_code=country.alpha_2,
                    city=city,
                    remote=is_remote_hint,
                    confidence="alias",
                    raw_text=location_text,
                )

    # Tier 4: curated city -> country table (Kenya-first). Handles bare
    # city names with no country given at all -- very common in
    # Kenyan/Gulf postings.
    for token in tokens:
        country_name = CITY_COUNTRY_MAP.get(token.strip().lower())
        if country_name:
            country = _lookup_country_exact(country_name)
            if country:
                return NormalizedLocation(
                    country=country.name,
                    country_code=country.alpha_2,
                    city=token.strip(),
                    remote=is_remote_hint,
                    confidence="city_table",
                    raw_text=location_text,
                )

    # Tier 5: best-effort exact-country-name substring scan of the full
    # text (catches e.g. "Remote - Kenya based" where the country isn't
    # cleanly comma-separated). Uses real country names only, no fuzzy
    # matching.
    lowered = location_text.lower()
    for country in pycountry.countries:
        if country.name.lower() in lowered:
            return NormalizedLocation(
                country=country.name,
                country_code=country.alpha_2,
                remote=is_remote_hint,
                confidence="substring",
                raw_text=location_text,
            )

    # Tier 5b: alias substring scan -- gives Gulf (and any future
    # region added to PROJECT_ALIASES) the same loose-text coverage
    # Kenya already gets from tier 5, e.g. "Remote - UAE based" now
    # resolves country the same way "Remote - Kenya based" does.
    # Word-boundary matched to avoid false positives (e.g. "us" inside
    # "Mauritius"). PROJECT_ALIASES is the single configurable source
    # -- add a new region there and this scan covers it automatically,
    # no code change needed here.
    for alias, country_name in PROJECT_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            country = _lookup_country_exact(country_name)
            if country:
                return NormalizedLocation(
                    country=country.name,
                    country_code=country.alpha_2,
                    remote=is_remote_hint,
                    confidence="alias_substring",
                    raw_text=location_text,
                )

    # Tier 6: unknown -- caller must skip the location criterion.
    if is_remote_hint:
        return NormalizedLocation(remote=True, confidence="substring", raw_text=location_text)

    return None
