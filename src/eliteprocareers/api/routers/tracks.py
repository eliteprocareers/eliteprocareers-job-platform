from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.schemas import (
    CreateTrackRequest,
    MatchTriggerResponse,
    UpdateTrackRequest,
)
from eliteprocareers.matching.matching_service import run_matching_for_track_tracked
from eliteprocareers.matching.models import MatchingRun
from eliteprocareers.matching.repository import MatchingRunRepository
from eliteprocareers.profiles.models import CVTrack
from eliteprocareers.profiles.track_repository import TrackRepository

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("", response_model=list[CVTrack])
def list_my_tracks(current_user: CurrentUser = Depends(get_current_user)) -> list[CVTrack]:
    """All CV tracks belonging to the authenticated user."""
    return TrackRepository(current_user.db).list_tracks(current_user.id)


def _get_owned_track(track_id: UUID, current_user: CurrentUser) -> CVTrack:
    """Fetch a track and verify it belongs to current_user.

    get_track() itself has no user filter (it's a plain id lookup), so
    ownership must be checked here explicitly -- returns 404 either way
    (track missing, or exists but belongs to someone else) rather than a
    403, so a caller can't use the distinction to enumerate other users'
    track ids.
    """
    track = TrackRepository(current_user.db).get_track(track_id)
    if track is None or track.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="CV track not found."
        )
    return track


@router.get("/{track_id}", response_model=CVTrack)
def get_track(
    track_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> CVTrack:
    return _get_owned_track(track_id, current_user)


@router.post("", response_model=CVTrack, status_code=status.HTTP_201_CREATED)
def create_track(
    payload: CreateTrackRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> CVTrack:
    """Create a new CV track for the authenticated user. user_id always
    comes from the resolved token (current_user.id), never from the
    request body -- same rule dependencies.py documents for every other
    handler.
    """
    return TrackRepository(current_user.db).create_track(
        user_id=current_user.id, **payload.model_dump()
    )


@router.put("/{track_id}", response_model=CVTrack)
def update_track(
    track_id: UUID,
    payload: UpdateTrackRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> CVTrack:
    """Partial update of an existing track. Ownership verified first via
    _get_owned_track() (same 404-for-both pattern as get_track). Only
    fields actually present in the request body are sent to the
    repository.
    """
    _get_owned_track(track_id, current_user)  # 404 if missing/not owned
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update.",
        )
    return TrackRepository(current_user.db).update_track(track_id, **fields)


@router.post(
    "/{track_id}/match",
    response_model=MatchTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_matching(
    track_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> MatchTriggerResponse:
    """Kicks off a Stage-1 + Stage-2 matching run for this track in the
    background and returns immediately (202, not 200) -- a real run
    takes several minutes against ~3000 jobs (see run_matching.py's own
    progress-throttling comment), so running it inline would hang the
    HTTP request for that whole time.

    Creates a matching_runs row synchronously (before returning) so the
    client always gets a real run_id to poll, then hands the tracked
    run to BackgroundTasks. Poll GET /tracks/{track_id}/match-status/
    {run_id} for real completion status -- replaces the earlier
    client-side timed-poll workaround against .../matches.
    """
    track = _get_owned_track(track_id, current_user)

    run_repo = MatchingRunRepository(current_user.db)
    existing_run = run_repo.get_running_run_for_track(track_id)
    if existing_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A matching run (run_id={existing_run.id}) is already in "
                f"progress for this track. Poll GET /tracks/{track_id}/"
                f"match-status/{existing_run.id} instead of starting a new one."
            ),
        )

    run = run_repo.create_run(user_id=current_user.id, cv_track_id=track_id)
    background_tasks.add_task(
        run_matching_for_track_tracked,
        current_user.id,
        track_id,
        run.id,
        current_user.db,
        current_user.organization_id,
    )
    return MatchTriggerResponse(
        track_id=track_id,
        track_name=track.track_name,
        run_id=run.id,
        status="started",
        message=(
            "Matching run started in the background. "
            "Poll GET /tracks/{track_id}/match-status/{run_id} "
            "for real completion status."
        ),
    )


@router.get(
    "/{track_id}/match-status/{run_id}",
    response_model=MatchingRun,
)
def get_match_status(
    track_id: UUID,
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> MatchingRun:
    """Poll endpoint for a matching run's real status -- running,
    completed, or failed -- with jobs_processed/jobs_total for progress.
    track_id is verified via _get_owned_track (404 if not owned) even
    though the run itself already carries user_id, for the same
    can't-enumerate-other-users'-ids reason as every other track_id path
    param in this router.
    """
    _get_owned_track(track_id, current_user)
    run = MatchingRunRepository(current_user.db).get_run(run_id)
    if run is None or run.user_id != current_user.id or run.cv_track_id != track_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Matching run not found."
        )
    return run
