"""
Extracts normalized `jobs.attributes` fields from each connector's
already-stored `raw_json` -- no new HTTP requests, just a transform on
data already sitting in the database.

MyJobMag is the only source implemented so far, per the Kenya-first
priority (see handover) and because its raw_json genuinely has the
richest usable signal of the four connectors -- confirmed live
2026-07-19 by pulling every distinct value of every raw_json key across
every MyJobMag job currently in the `jobs` table (not guessed):

- Job Type: e.g. "Full Time", "Contract , Full Time", "Full Time , Hybrid".
  Conflates employment_type and work_mode in one comma-separated field --
  confirmed live this is genuinely how MyJobMag writes it, not a parsing
  artifact. Split apart into the two attributes keys the filtering engine
  actually checks separately.
- Experience: e.g. "3 years", "2 - 3 years", "" (56 jobs have no value).
  Real years, not a seniority label -- bucketed into entry/mid/senior/lead
  using the MINIMUM year in any range (a "5 - 8 years" job's real bar to
  clear is 5, not 8) via thresholds confirmed with the user: 0-1 entry,
  2-4 mid, 5-8 senior, 9+ lead.
- Job Field: e.g. "Data, Business Analysis and AI , ICT / Computer" --
  genuinely multi-value free text (30+ distinct categories seen), not a
  controlled vocabulary. Stored as a list; paired with the check_industry
  update in filtering.py that matches on any overlap rather than a single
  exact value.
- Salary Range: only 4 of ~300 sampled jobs have it at all -- too sparse
  to be worth extracting in this pass. Deliberately skipped; revisit if
  MyJobMag's listings show more salary transparency later.
"""
import re

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


def _bucket_seniority(raw_experience: str | None) -> str | None:
    """Buckets MyJobMag's free-text "Experience" years into a seniority
    label. Uses the MINIMUM year found (a range's real floor) -- e.g.
    "5 - 8 years" buckets as senior (5), not lead (8), since 5 years is
    the actual bar a candidate has to clear.

    Thresholds confirmed with the user: 0-1 entry, 2-4 mid, 5-8 senior,
    9+ lead.
    """
    if not raw_experience:
        return None

    years = [int(n) for n in _YEARS_PATTERN.findall(raw_experience)]
    if not years:
        return None

    floor_years = min(years)

    if floor_years <= 1:
        return "entry"
    elif floor_years <= 4:
        return "mid"
    elif floor_years <= 8:
        return "senior"
    else:
        return "lead"


def _extract_industries(raw_field: str | None) -> list[str] | None:
    """Splits MyJobMag's "Job Field" into a list of cleaned category
    strings. Genuinely multi-value on real data (e.g. "Data, Business
    Analysis and AI\xa0 , ICT / Computer") -- but naively splitting on
    every comma is WRONG: some individual category names contain their
    own internal comma (e.g. "Data, Business Analysis and AI" is ONE
    category, not two). Confirmed live across every multi-value example
    in the real data that the actual separator is always a comma
    immediately preceded by a non-breaking space (\xa0) -- a category's
    own internal comma never has \xa0 before it. Splits on that pattern
    specifically, not on bare commas.
    """
    if not raw_field:
        return None

    categories = [
        part.replace("\xa0", "").strip()
        for part in re.split(r"\xa0\s*,", raw_field)
    ]
    categories = [c for c in categories if c]
    return categories or None


def extract_myjobmag_attributes(raw_json: dict) -> dict:
    """Maps one MyJobMag job's raw_json (the key_info dict the connector
    already stores -- keys confirmed live: 'Job Type', 'Experience',
    'Qualification', 'Job Field', 'Location', 'Salary Range') into the
    jobs.attributes shape. Only includes keys it has real data for --
    never writes a key with a None/empty value, so downstream SKIP
    logic in filtering.py still behaves correctly on missing data.
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

    industries = _extract_industries(raw_json.get("Job Field"))
    if industries is not None:
        attributes["industry"] = industries

    return attributes
