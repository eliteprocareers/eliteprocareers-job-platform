from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.schemas import (
    CreateTrackRequest,
    MatchTriggerResponse,
    UpdateTrackRequest,
)
from eliteprocareers.matching.matching_service import run_matching_for_track
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
    HTTP request for that whole time. Poll GET /tracks/{track_id}/matches
    afterward for updated scores.
    """
    track = _get_owned_track(track_id, current_user)
    background_tasks.add_task(
        run_matching_for_track, current_user.id, track_id, current_user.db
    )
    return MatchTriggerResponse(
        track_id=track_id,
        track_name=track.track_name,
        status="started",
        message=(
            "Matching run started in the background. "
            "Poll GET /tracks/{track_id}/matches for updated results."
        ),
    )
