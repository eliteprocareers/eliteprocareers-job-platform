from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
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
