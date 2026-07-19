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
