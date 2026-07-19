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
from eliteprocareers.profiles.models import CVTrack


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
    """Exact match against job.attributes['industry'] vs
    track.industries. Same shape as check_employment_type and
    check_seniority -- connector-populated, no normalization layer
    needed.

    NOTE: as of migration 0003, no connector populates
    attributes['industry'] yet -- this criterion will SKIP on all
    current real data until a connector is updated to extract it.
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

    if job_industry in track.industries:
        return CriterionResult(
            criterion="industry",
            outcome=FilterOutcome.PASS,
            detail=f"{job_industry} is in industries",
        )

    return CriterionResult(
        criterion="industry",
        outcome=FilterOutcome.FAIL,
        detail=f"{job_industry} is not in industries {track.industries}",
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
