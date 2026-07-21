from uuid import UUID

from fastapi import APIRouter, Depends, Query

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.routers.tracks import _get_owned_track
from eliteprocareers.api.schemas import MatchWithJob
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.repository import UserJobMatchRepository

router = APIRouter(prefix="/tracks", tags=["matches"])


@router.get("/{track_id}/matches", response_model=list[MatchWithJob])
def list_matches_for_track(
    track_id: UUID,
    min_score: float | None = Query(
        default=None, ge=0.0, le=1.0, description="Only return matches at or above this score."
    ),
    limit: int = Query(default=50, ge=1, le=348),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[MatchWithJob]:
    """Best-first list of this track's scored matches, joined with job
    title/company/url/location. Ownership of track_id is verified first
    (404 if it doesn't belong to the caller) -- the underlying matches
    table also carries user-scoped RLS as a second, independent layer,
    since this endpoint uses current_user's own token, not service_role.
    """
    _get_owned_track(track_id, current_user)

    match_repo = UserJobMatchRepository(current_user.db)
    matches = match_repo.list_matches_for_track(track_id, min_score=min_score)
    matches = matches[:limit]

    job_repo = JobRepository(current_user.db)
    jobs_by_id = {job.id: job for job in job_repo.get_jobs_by_ids([m.job_id for m in matches])}

    results: list[MatchWithJob] = []
    for m in matches:
        job = jobs_by_id.get(m.job_id)
        if job is None:
            continue
        results.append(
            MatchWithJob(
                match_id=m.id,
                job_id=m.job_id,
                match_score=m.match_score,
                ai_rationale=m.ai_rationale,
                scored_at=m.scored_at,
                job_title=job.title,
                job_company=job.company,
                job_url=job.url,
                job_location=job.location,
            )
        )
    return results
