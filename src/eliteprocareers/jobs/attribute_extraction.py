"""
Extracts normalized `jobs.attributes` fields from each connector's
already-stored `raw_json` -- no new HTTP requests, just a transform on
data already sitting in the database.

Two sources implemented: MyJobMag and BrighterMonday, both confirmed
live against real raw_json (2026-07-19/07-20), per the Kenya-first
priority.

Industry/category values from BOTH sources now go through
taxonomy/industries.py's mapping tables + normalize_categories()
instead of being stored as raw source strings -- this is what lets
check_industry compare a MyJobMag job against a BrighterMonday job
against a candidate's track on one shared vocabulary, instead of three
incompatible ones. Every extract_*_attributes() function returns
(attributes, unmapped) -- unmapped is every raw category value that
had no entry in that source's mapping table, surfaced by the backfill
scripts rather than silently dropped.

MyJobMag raw_json fields used (confirmed live):
- Job Type: e.g. "Full Time", "Contract , Full Time", "Full Time , Hybrid" --
  conflates employment_type and work_mode in one field; split apart.
- Experience: e.g. "3 years", "2 - 3 years", "" (56/246 empty) -- bucketed
  by the MINIMUM year in any range via thresholds confirmed with the
  user: 0-1 entry, 2-4 mid, 5-8 senior, 9+ lead.
- Job Field: genuinely multi-value free text, split on \xa0-preceded
  commas (not every comma -- some category names contain their own
  comma), then mapped through SOURCE_MYJOBMAG_JOB_FIELD_MAP.
- Salary Range: only 4/~300 sampled -- too sparse, skipped.

BrighterMonday raw_json fields used (confirmed live, 80 jobs):
- employmentType: schema.org values, e.g. "FULL_TIME" (76), "CONTRACTOR" (3),
  and one list value "['INTERN', 'VOLUNTEER']" -- takes the first token
  that matches a known employment_type; VOLUNTEER has no equivalent in
  this project's vocabulary and is silently skipped (not FAIL, not guessed).
- jobLocationType: only value seen is "TELECOMMUTE" (4/80 jobs) -> remote.
  Absent on the other 76 -- NOT treated as onsite, same non-inference
  rule as everywhere else in this module.
- experienceRequirements.monthsOfExperience: real months, converted to
  a year-floor (months // 12) and bucketed with the same thresholds as
  MyJobMag's Experience field.
- industry + occupationalCategory: both genuinely populated (confirmed
  live, 17 + 21 distinct values respectively, "Unspecified" sentinels
  mapped to None), combined into one deduplicated canonical list.
- baseSalary: schema.org MonetaryAmount, e.g. {"value": {"minValue":...,
  "maxValue":..., "unitText": "MONTH"}, "currency": "KES"} -- confirmed
  live, 14/80 jobs sampled, unitText is MONTH on every sample seen so
  far (0 KES-15K band is a real low bracket, not a "not disclosed"
  sentinel -- confirmed by checking all 14 sampled rows, values are
  self-consistent 15K-wide bands throughout). Extracted into
  salary_min/salary_max/salary_currency ONLY when unitText == "MONTH" --
  no unit conversion in this project, so a future YEAR/HOUR value is
  silently skipped rather than guessed at, same non-guessing rule as
  everywhere else in this module.
"""
import re

from eliteprocareers.taxonomy.industries import (
    SOURCE_BRIGHTERMONDAY_INDUSTRY_MAP,
    SOURCE_BRIGHTERMONDAY_OCCUPATIONAL_CATEGORY_MAP,
    SOURCE_MYJOBMAG_JOB_FIELD_MAP,
    normalize_categories,
)

# Job Type token -> normalized value, split from the comma-separated
# raw string. Two disjoint vocabularies live in the same field on
# MyJobMag -- confirmed live, not assumed.
_EMPLOYMENT_TYPE_TOKENS = {
    "Full Time": "full_time",
    "Part Time": "part_time",
    "Contract": "contract",
    "Internship": "internship",  # not observed live yet, kept for forward-compat
}
_WORK_MODE_TOKENS = {
    "Onsite": "onsite",
    "Hybrid": "hybrid",
    "Remote": "remote",  # not observed live yet, kept for forward-compat
}

_YEARS_PATTERN = re.compile(r"\d+")


def _extract_job_type(raw_type: str | None) -> tuple[str | None, str | None]:
    """Splits MyJobMag's "Job Type" into (employment_type, work_mode).

    Real data has entries naming more than one employment-type token at
    once (e.g. "Contract , Full Time", 7 of ~247 non-empty values) --
    ambiguous by construction, not a parsing bug. Takes the FIRST
    matching token in each vocabulary, in the order MyJobMag wrote it,
    since check_employment_type/check_work_mode in filtering.py both
    expect a single scalar, not a list -- deliberately not changing that
    contract in this pass. This is a documented simplification, not a
    guess: it affects only ~3% of MyJobMag's Job Type values.
    """
    if not raw_type:
        return None, None

    employment_type: str | None = None
    work_mode: str | None = None

    for token in (t.strip() for t in raw_type.split(",")):
        if employment_type is None and token in _EMPLOYMENT_TYPE_TOKENS:
            employment_type = _EMPLOYMENT_TYPE_TOKENS[token]
        if work_mode is None and token in _WORK_MODE_TOKENS:
            work_mode = _WORK_MODE_TOKENS[token]

    return employment_type, work_mode


def _bucket_seniority_from_years(floor_years: int) -> str:
    """Thresholds confirmed with the user: 0-1 entry, 2-4 mid, 5-8
    senior, 9+ lead. Shared by both sources -- MyJobMag supplies
    floor_years directly from its "Experience" text, BrighterMonday
    supplies it as monthsOfExperience // 12.
    """
    if floor_years <= 1:
        return "entry"
    elif floor_years <= 4:
        return "mid"
    elif floor_years <= 8:
        return "senior"
    else:
        return "lead"


def _bucket_seniority(raw_experience: str | None) -> str | None:
    """Buckets MyJobMag's free-text "Experience" years into a seniority
    label. Uses the MINIMUM year found (a range's real floor) -- e.g.
    "5 - 8 years" buckets as senior (5), not lead (8).
    """
    if not raw_experience:
        return None

    years = [int(n) for n in _YEARS_PATTERN.findall(raw_experience)]
    if not years:
        return None

    return _bucket_seniority_from_years(min(years))


def _split_myjobmag_job_field(raw_field: str | None) -> list[str]:
    """Splits MyJobMag's "Job Field" into raw category strings. Splits
    on a comma immediately preceded by a non-breaking space (\xa0) --
    confirmed live this is the real separator; a category's own
    internal comma (e.g. "Data, Business Analysis and AI") never has
    \xa0 before it, so a naive split on every comma would be wrong.
    """
    if not raw_field:
        return []

    categories = [
        part.replace("\xa0", "").strip()
        for part in re.split(r"\xa0\s*,", raw_field)
    ]
    return [c for c in categories if c]


def extract_myjobmag_attributes(raw_json: dict) -> tuple[dict, list[str]]:
    """Maps one MyJobMag job's raw_json into the jobs.attributes shape.
    Only includes keys it has real data for -- never writes a key with
    a None/empty value, so downstream SKIP logic in filtering.py still
    behaves correctly on missing data.

    Returns (attributes, unmapped_industries) -- unmapped_industries is
    every raw "Job Field" category not found in
    SOURCE_MYJOBMAG_JOB_FIELD_MAP, for the backfill script to report
    rather than silently drop.
    """
    attributes: dict = {}

    employment_type, work_mode = _extract_job_type(raw_json.get("Job Type"))
    if employment_type is not None:
        attributes["employment_type"] = employment_type
    if work_mode is not None:
        attributes["work_mode"] = work_mode

    seniority = _bucket_seniority(raw_json.get("Experience"))
    if seniority is not None:
        attributes["seniority_level"] = seniority

    raw_categories = _split_myjobmag_job_field(raw_json.get("Job Field"))
    canonical, unmapped = normalize_categories(raw_categories, SOURCE_MYJOBMAG_JOB_FIELD_MAP)
    if canonical:
        attributes["industry"] = canonical
    if raw_categories:
        attributes["industry_raw"] = raw_categories

    return attributes, unmapped


def extract_brightermonday_attributes(raw_json: dict) -> tuple[dict, list[str]]:
    """Maps one BrighterMonday job's raw_json (schema.org JobPosting
    shape) into the jobs.attributes shape. Only includes keys it has
    real data for.

    Returns (attributes, unmapped_industries), same contract as
    extract_myjobmag_attributes.
    """
    attributes: dict = {}
    unmapped: list[str] = []

    raw_employment = raw_json.get("employmentType")
    if raw_employment:
        tokens = raw_employment if isinstance(raw_employment, list) else [raw_employment]
        employment_map = {
            "FULL_TIME": "full_time",
            "PART_TIME": "part_time",
            "CONTRACTOR": "contract",
            "INTERN": "internship",
        }
        for token in tokens:
            if token in employment_map:
                attributes["employment_type"] = employment_map[token]
                break

    if raw_json.get("jobLocationType") == "TELECOMMUTE":
        attributes["work_mode"] = "remote"

    experience = raw_json.get("experienceRequirements")
    months = experience.get("monthsOfExperience") if isinstance(experience, dict) else None
    if months is not None:
        attributes["seniority_level"] = _bucket_seniority_from_years(months // 12)

    canonical: list[str] = []
    for raw_value, mapping in (
        (raw_json.get("industry"), SOURCE_BRIGHTERMONDAY_INDUSTRY_MAP),
        (raw_json.get("occupationalCategory"), SOURCE_BRIGHTERMONDAY_OCCUPATIONAL_CATEGORY_MAP),
    ):
        if not raw_value:
            continue
        c, u = normalize_categories([raw_value], mapping)
        canonical.extend(c)
        unmapped.extend(u)

    seen: set[str] = set()
    deduped: list[str] = []
    for c in canonical:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    if deduped:
        attributes["industry"] = deduped

    base_salary = raw_json.get("baseSalary")
    if isinstance(base_salary, dict):
        salary_value = base_salary.get("value")
        if isinstance(salary_value, dict) and salary_value.get("unitText") == "MONTH":
            salary_min = salary_value.get("minValue")
            salary_max = salary_value.get("maxValue")
            currency = base_salary.get("currency")
            if salary_min is not None:
                attributes["salary_min"] = salary_min
            if salary_max is not None:
                attributes["salary_max"] = salary_max
            if currency:
                attributes["salary_currency"] = currency

    raw_categories = [v for v in (raw_json.get("industry"), raw_json.get("occupationalCategory")) if v]
    if raw_categories:
        attributes["industry_raw"] = raw_categories

    return attributes, unmapped
