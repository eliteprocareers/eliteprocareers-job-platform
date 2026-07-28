from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

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
def list_my_tracks(
    candidate_user_id: UUID | None = Query(
        default=None,
        description=(
            "List a specific candidate's tracks instead of the caller's own "
            "-- for an org admin/owner, or a manager/staff specifically "
            "assigned to that candidate (migration 0015). Omit to list the "
            "caller's own tracks, the original and still-default behavior."
        ),
    ),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[CVTrack]:
    """All CV tracks belonging to the authenticated user, or (if
    candidate_user_id is provided) belonging to that candidate --
    visibility is entirely RLS's job (can_view_org_resource(), migration
    0015), same as every other read in this router now. Asking for a
    candidate_user_id the caller can't see just returns an empty list,
    not an error -- RLS filters the underlying select, this endpoint
    doesn't need its own permission check on top of that.
    """
    target_user_id = candidate_user_id if candidate_user_id is not None else current_user.id
    return TrackRepository(current_user.db).list_tracks(target_user_id)


def _get_visible_track(track_id: UUID, current_user: CurrentUser) -> CVTrack:
    """Fetch a track the caller is allowed to see or manage.

    get_track() itself has no user filter (it's a plain id lookup) --
    visibility is entirely RLS's job (can_view_org_resource(), migration
    0015): the caller's own tracks, or an org admin/owner, or (if
    sharing_mode='full') any org member, or a manager/staff specifically
    assigned to this track's candidate. If RLS returned the row at all,
    the caller is allowed to see and manage it -- there is deliberately
    NO additional `track.user_id != current_user.id` check here anymore.

    That check used to exist and was, in effect, silently overriding
    migration 0015's RLS loosening: RLS started permitting assigned
    managers/staff to see a candidate's tracks, but this function kept
    rejecting anyone except the track's literal owner regardless, so
    nothing about assigned-only visibility was actually reachable
    through the API until this fix. Renamed from _get_owned_track to
    _get_visible_track to name what it actually checks now -- kept as
    the single choke point every other router (applications.py,
    documents.py, matches.py) already goes through, so fixing it here
    fixes all of them at once.

    Still 404s (not None-returns) for a track that doesn't exist OR
    isn't visible to this caller -- same can't-enumerate-other-users'-
    ids reasoning as before, just no longer a stricter check than RLS
    itself already enforces.
    """
    track = TrackRepository(current_user.db).get_track(track_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="CV track not found."
        )
    return track


# Old name kept as an alias -- applications.py, documents.py, matches.py
# all import _get_owned_track by that name; renaming the import sites
# too is a larger diff than this fix needs to make, and the alias
# keeps the two files honest about being the same function rather than
# risking a copy-paste drift between them.
_get_owned_track = _get_visible_track


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

    Scope boundary, deliberate (2026-07-28): unlike every other
    endpoint in this router, this one is NOT yet assignment-aware.
    run_repo.create_run() and run_matching_for_track_tracked() both
    still use current_user.id, not track.user_id -- fine for the
    normal self-service case (they're the same value), but for an
    assigned manager/staff triggering a run on an assigned candidate's
    track, this would misattribute the resulting user_job_matches rows
    to the staff member instead of the candidate. Also, matching_runs
    itself has no organization_id column and RLS restricted to
    user_id = auth.uid() only (confirmed by reading it directly) --
    so even fixing the user_id here wouldn't let the candidate or other
    assigned staff poll the run's status afterward. Needs real design
    work in matching_service.py, not a one-line change -- not done
    this session, flagged rather than silently left looking finished.
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
