"""
Stage-1 filtering engine -- hard pass/skip/fail checks run against a
CVTrack's structured preferences (migration 0003) before a job is even
considered for Stage-2 embedding-based scoring (scoring/embeddings.py).

Built criterion by criterion, each one tested against real data before
the next is added. Location is first since matching/location.py is
already built and tested.

Design rule carried over from location.py: an unset candidate
preference is NON-RESTRICTIVE (empty list = "no preference", not
"excludes everything"), and an unresolvable job attribute is UNKNOWN,
never treated as a failure. Only a genuine, resolved mismatch is a
real FAIL.
"""
from enum import Enum

from pydantic import BaseModel

from eliteprocareers.jobs.models import Job
from eliteprocareers.matching.location import normalize_location
from eliteprocareers.profiles.models import CandidateProfile, CVTrack


class FilterOutcome(str, Enum):
    PASS = "pass"
    SKIP = "skip"
    FAIL = "fail"


class CriterionResult(BaseModel):
    criterion: str
    outcome: FilterOutcome
    detail: str | None = None


def check_employment_type(track: CVTrack, job: Job) -> CriterionResult:
    """Exact match against job.attributes['employment_type'] (e.g.
    'full_time', 'part_time', 'contract', 'internship'). No
    normalization layer needed here unlike location -- this is a
    closed, small vocabulary that connectors populate directly, not
    free text a job board writes in its own words.

    NOTE: as of migration 0003, no connector populates
    attributes['employment_type'] yet -- this criterion will SKIP on
    all current real data until a connector is updated to extract it.
    That's correct, expected behavior (unknown = skip), not a bug.
    """
    if not track.employment_types:
        return CriterionResult(
            criterion="employment_type",
            outcome=FilterOutcome.SKIP,
            detail="no employment_types set on this track",
        )

    job_employment_type = job.attributes.get("employment_type")

    if not job_employment_type:
        return CriterionResult(
            criterion="employment_type",
            outcome=FilterOutcome.SKIP,
            detail="job has no employment_type attribute (connector doesn't populate it yet)",
        )

    if job_employment_type in track.employment_types:
        return CriterionResult(
            criterion="employment_type",
            outcome=FilterOutcome.PASS,
            detail=f"{job_employment_type} is in employment_types",
        )

    return CriterionResult(
        criterion="employment_type",
        outcome=FilterOutcome.FAIL,
        detail=f"{job_employment_type} is not in employment_types {track.employment_types}",
    )


def check_seniority(track: CVTrack, job: Job) -> CriterionResult:
    """Exact match against job.attributes['seniority_level'] (e.g.
    'entry', 'mid', 'senior', 'lead', 'executive') vs
    track.seniority_levels. Same shape as check_employment_type --
    closed vocabulary, connector-populated, no normalization layer
    needed.

    NOTE: as of migration 0003, no connector populates
    attributes['seniority_level'] yet -- this criterion will SKIP on
    all current real data until a connector is updated to extract it.
    """
    if not track.seniority_levels:
        return CriterionResult(
            criterion="seniority",
            outcome=FilterOutcome.SKIP,
            detail="no seniority_levels set on this track",
        )

    job_seniority = job.attributes.get("seniority_level")

    if not job_seniority:
        return CriterionResult(
            criterion="seniority",
            outcome=FilterOutcome.SKIP,
            detail="job has no seniority_level attribute (connector doesn't populate it yet)",
        )

    if job_seniority in track.seniority_levels:
        return CriterionResult(
            criterion="seniority",
            outcome=FilterOutcome.PASS,
            detail=f"{job_seniority} is in seniority_levels",
        )

    return CriterionResult(
        criterion="seniority",
        outcome=FilterOutcome.FAIL,
        detail=f"{job_seniority} is not in seniority_levels {track.seniority_levels}",
    )


def check_industry(track: CVTrack, job: Job) -> CriterionResult:
    """Match against job.attributes['industry'] vs track.industries.

    Unlike check_employment_type/check_seniority, job.attributes['industry']
    is genuinely MULTI-VALUE on real data -- MyJobMag's "Job Field" source
    field commonly lists 2-3 categories for one job (confirmed live,
    e.g. "Data, Business Analysis and AI" + "ICT / Computer" as two
    distinct categories on the same posting). A job passes if ANY of its
    categories overlaps track.industries, not just an exact single-value
    match -- a job tagged both "Data, Business Analysis and AI" and
    "ICT / Computer" should match a candidate who only listed "ICT /
    Computer" as a desired industry. Still accepts a single string (not
    a list) for backward-compatibility with any future connector that
    only ever writes one value.
    """
    if not track.industries:
        return CriterionResult(
            criterion="industry",
            outcome=FilterOutcome.SKIP,
            detail="no industries set on this track",
        )

    job_industry = job.attributes.get("industry")

    if not job_industry:
        return CriterionResult(
            criterion="industry",
            outcome=FilterOutcome.SKIP,
            detail="job has no industry attribute (connector doesn't populate it yet)",
        )

    job_industries = job_industry if isinstance(job_industry, list) else [job_industry]
    matched = [i for i in job_industries if i in track.industries]

    if matched:
        return CriterionResult(
            criterion="industry",
            outcome=FilterOutcome.PASS,
            detail=f"{matched} overlaps industries {track.industries}",
        )

    return CriterionResult(
        criterion="industry",
        outcome=FilterOutcome.FAIL,
        detail=f"{job_industries} has no overlap with industries {track.industries}",
    )


def check_work_mode(track: CVTrack, job: Job) -> CriterionResult:
    """Match against track.work_mode (e.g. 'remote', 'hybrid',
    'onsite'). Two-tier signal, unlike the previous three criteria:

    1. job.attributes['work_mode'] (structured, connector-populated --
       not populated by any connector yet, same as the other criteria).
    2. Fallback: normalize_location()'s remote flag (from
       matching/location.py). If a job's location text says "Remote",
       we can confidently call job_work_mode='remote' TODAY, without
       waiting on connector work -- unlike employment_type/seniority/
       industry, which have no fallback and SKIP on all real data.

    IMPORTANT: the fallback can only ever positively identify 'remote'.
    If normalize_location() does NOT flag a job remote, that does NOT
    mean onsite -- location text alone can't distinguish onsite from
    hybrid. So a non-remote signal from tier 2 stays SKIP, never FAIL.
    Guessing onsite vs hybrid from location text would risk wrongly
    failing a real hybrid job.
    """
    if not track.work_mode:
        return CriterionResult(
            criterion="work_mode",
            outcome=FilterOutcome.SKIP,
            detail="no work_mode set on this track",
        )

    job_work_mode = job.attributes.get("work_mode")
    detail_source = "job.attributes"

    if not job_work_mode:
        normalized = normalize_location(job.location, job.attributes)
        if normalized is not None and normalized.remote:
            job_work_mode = "remote"
            detail_source = "location remote-flag fallback"

    if not job_work_mode:
        return CriterionResult(
            criterion="work_mode",
            outcome=FilterOutcome.SKIP,
            detail="job has no work_mode attribute and location text isn't flagged remote",
        )

    if job_work_mode in track.work_mode:
        return CriterionResult(
            criterion="work_mode",
            outcome=FilterOutcome.PASS,
            detail=f"{job_work_mode} is in work_mode (via {detail_source})",
        )

    return CriterionResult(
        criterion="work_mode",
        outcome=FilterOutcome.FAIL,
        detail=f"{job_work_mode} is not in work_mode {track.work_mode} (via {detail_source})",
    )


def check_relocation(track: CVTrack, job: Job, profile: CandidateProfile) -> CriterionResult:
    """Only fires when preferred_countries is EMPTY -- if the candidate
    already set an explicit country list, check_location owns that
    decision entirely and this criterion steps aside (SKIP) to avoid
    double-penalizing the same job for the same underlying reason.

    With no explicit preferred_countries:
    - willing_to_relocate=True -> SKIP, no restriction.
    - willing_to_relocate=False -> compare the job's country against
      the candidate's home country (profile.location). Mismatch means
      the candidate isn't willing to relocate for this job.

    Takes `profile` as a third argument (unlike every other criterion
    so far) because it's the only one that needs the candidate's own
    location, not just track preferences.
    """
    if track.preferred_countries:
        return CriterionResult(
            criterion="relocation",
            outcome=FilterOutcome.SKIP,
            detail="preferred_countries is set -- handled by check_location instead",
        )

    if track.willing_to_relocate:
        return CriterionResult(
            criterion="relocation",
            outcome=FilterOutcome.SKIP,
            detail="willing_to_relocate=True, no restriction",
        )

    job_normalized = normalize_location(job.location, job.attributes)
    if job_normalized is None or job_normalized.country is None:
        return CriterionResult(
            criterion="relocation",
            outcome=FilterOutcome.SKIP,
            detail=f"job location could not be resolved (raw: {job.location!r})",
        )

    home_normalized = normalize_location(profile.location, None)
    if home_normalized is None or home_normalized.country is None:
        return CriterionResult(
            criterion="relocation",
            outcome=FilterOutcome.SKIP,
            detail=f"candidate home location could not be resolved (raw: {profile.location!r})",
        )

    if job_normalized.country == home_normalized.country:
        return CriterionResult(
            criterion="relocation",
            outcome=FilterOutcome.PASS,
            detail=f"job is in candidate's home country ({home_normalized.country})",
        )

    return CriterionResult(
        criterion="relocation",
        outcome=FilterOutcome.FAIL,
        detail=(
            f"job is in {job_normalized.country}, candidate's home country is "
            f"{home_normalized.country} and willing_to_relocate=False"
        ),
    )


def check_visa_sponsorship(track: CVTrack, job: Job) -> CriterionResult:
    """visa_sponsorship_required=None or False both mean 'no
    restriction' -- only an explicit True triggers a check. Mirrors the
    job.attributes pattern from employment_type/seniority/industry:
    missing job data means SKIP, not FAIL.
    """
    if not track.visa_sponsorship_required:
        return CriterionResult(
            criterion="visa_sponsorship",
            outcome=FilterOutcome.SKIP,
            detail="visa sponsorship not required by this track",
        )

    job_offers_sponsorship = job.attributes.get("visa_sponsorship")

    if job_offers_sponsorship is None:
        return CriterionResult(
            criterion="visa_sponsorship",
            outcome=FilterOutcome.SKIP,
            detail="job doesn't specify visa sponsorship (connector doesn't populate it yet)",
        )

    if job_offers_sponsorship:
        return CriterionResult(
            criterion="visa_sponsorship",
            outcome=FilterOutcome.PASS,
            detail="job offers visa sponsorship",
        )

    return CriterionResult(
        criterion="visa_sponsorship",
        outcome=FilterOutcome.FAIL,
        detail="candidate requires visa sponsorship, job does not offer it",
    )


def check_salary(track: CVTrack, job: Job) -> CriterionResult:
    """Only track.salary_expectation_min acts as a hard floor for this
    criterion -- salary_expectation_max is informational (top of the
    candidate's expected range for CV/negotiation purposes) and is
    never used to fail a job for paying too much.

    Currency mismatch: if both track.salary_currency and
    job.attributes['salary_currency'] are set and differ, the two
    numbers aren't safely comparable -- no FX conversion in MVP, so
    this SKIPs rather than guessing and risking a wrong FAIL.

    Job-side reference figure: salary_max if the connector populated
    it, else salary_min. Preferring the job's max gives the job the
    benefit of the doubt -- a range that only dips below the floor at
    its lower end shouldn't be penalized if its upper end clears it.
    """
    if track.salary_expectation_min is None:
        return CriterionResult(
            criterion="salary",
            outcome=FilterOutcome.SKIP,
            detail="no salary_expectation_min set on this track",
        )

    job_currency = job.attributes.get("salary_currency")
    if track.salary_currency and job_currency and track.salary_currency != job_currency:
        return CriterionResult(
            criterion="salary",
            outcome=FilterOutcome.SKIP,
            detail=(
                f"currency mismatch ({track.salary_currency} vs "
                f"{job_currency}) -- not safely comparable, no FX conversion in MVP"
            ),
        )

    job_salary_max = job.attributes.get("salary_max")
    job_salary_min = job.attributes.get("salary_min")
    job_reference = job_salary_max if job_salary_max is not None else job_salary_min

    if job_reference is None:
        return CriterionResult(
            criterion="salary",
            outcome=FilterOutcome.SKIP,
            detail="job has no salary_min/salary_max attribute (connector doesn't populate it yet)",
        )

    if job_reference < track.salary_expectation_min:
        return CriterionResult(
            criterion="salary",
            outcome=FilterOutcome.FAIL,
            detail=(
                f"job's best known figure ({job_reference}) is below "
                f"salary_expectation_min ({track.salary_expectation_min})"
            ),
        )

    return CriterionResult(
        criterion="salary",
        outcome=FilterOutcome.PASS,
        detail=(
            f"job's best known figure ({job_reference}) meets "
            f"salary_expectation_min ({track.salary_expectation_min})"
        ),
    )


def check_location(track: CVTrack, job: Job) -> CriterionResult:
    """Country-level check only for now (state/city precision can be
    added later if real data shows it's needed). willing_to_relocate is
    NOT consulted here -- that's a separate criterion, since a candidate
    can be relocation-willing but still have a preferred_countries list
    (e.g. "Kenya or Gulf only").
    """
    if not track.preferred_countries:
        return CriterionResult(
            criterion="location",
            outcome=FilterOutcome.SKIP,
            detail="no preferred_countries set on this track",
        )

    normalized = normalize_location(job.location, job.attributes)

    if normalized is None or normalized.country is None:
        return CriterionResult(
            criterion="location",
            outcome=FilterOutcome.SKIP,
            detail=f"job location could not be resolved (raw: {job.location!r})",
        )

    if normalized.country in track.preferred_countries:
        return CriterionResult(
            criterion="location",
            outcome=FilterOutcome.PASS,
            detail=f"{normalized.country} is in preferred_countries",
        )

    return CriterionResult(
        criterion="location",
        outcome=FilterOutcome.FAIL,
        detail=f"{normalized.country} is not in preferred_countries {track.preferred_countries}",
    )


def run_stage1_filters(
    track: CVTrack, job: Job, profile: CandidateProfile
) -> list[CriterionResult]:
    """Runs every Stage-1 criterion against one (track, job) pair and
    returns all 8 results together, in a fixed order. This is the
    single place that knows every criterion exists and how to call
    it -- callers (e.g. the ingestion/matching pipeline) shouldn't
    need to import each check_* function individually.

    check_relocation is the only criterion needing `profile` (the
    candidate's own home location, not just track preferences) --
    every other criterion only needs track + job.
    """
    return [
        check_employment_type(track, job),
        check_seniority(track, job),
        check_industry(track, job),
        check_work_mode(track, job),
        check_relocation(track, job, profile),
        check_visa_sponsorship(track, job),
        check_salary(track, job),
        check_location(track, job),
    ]


def passes_stage1(results: list[CriterionResult]) -> bool:
    """The actual Stage-1 gate: a job passes iff no criterion FAILed.

    SKIP is neutral by design (every criterion above already treats
    unset preferences / unresolvable job data as SKIP, never FAIL) --
    a job with all 8 criteria SKIPping still passes here, since
    nothing was actually determined to be a mismatch. Only a genuine,
    resolved FAIL blocks a job from Stage-2 scoring.
    """
    return not any(r.outcome == FilterOutcome.FAIL for r in results)
