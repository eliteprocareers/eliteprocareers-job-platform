from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.routers.documents import _get_owned_job_with_match
from eliteprocareers.api.routers.tracks import _get_owned_track
from eliteprocareers.api.schemas import (
    ApplicationWithJob,
    CreateApplicationRequest,
    UpdateApplicationStatusRequest,
)
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.profiles.application_repository import ApplicationRepository
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import Application, ApplicationStatus, DocType

router = APIRouter(prefix="/tracks", tags=["applications"])


def _get_owned_application(
    track_id: UUID, application_id: UUID, current_user: CurrentUser
) -> Application:
    """Verify the track is owned by current_user and the application
    belongs to both that track and that user -- 404 in every failure
    case, same can't-enumerate-other-ids reasoning as the rest of this
    API.
    """
    _get_owned_track(track_id, current_user)
    application = ApplicationRepository(current_user.db).get_application(application_id)
    if (
        application is None
        or application.user_id != current_user.id
        or application.cv_track_id != track_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found."
        )
    return application


@router.post(
    "/{track_id}/jobs/{job_id}/applications",
    response_model=Application,
    status_code=status.HTTP_201_CREATED,
)
def create_application(
    track_id: UUID,
    job_id: UUID,
    payload: CreateApplicationRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Application:
    """Create a draft application for this track+job pair. Draft-and-queue
    model: this never submits anything to an employer or ATS -- it only
    tracks status, same as every other endpoint in this router. If a
    CV/cover letter/screening answer has already been generated for this
    job, their generated_documents rows are linked to the new application
    via application_id (best-effort -- a document that doesn't exist yet
    just isn't linked, not an error).
    """
    _get_owned_job_with_match(track_id, job_id, current_user)

    app_repo = ApplicationRepository(current_user.db)

    # uq_applications_track_job (migration 0010) enforces this at the DB
    # level too, but a pre-check here lets us return a clean 409 instead
    # of a raw DB error -- this is a direct user action (e.g. double-
    # clicking "Apply"), not a background race, so it deserves a real
    # error message rather than a 500.
    existing = app_repo.get_application_for_job_and_track(job_id, track_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An application already exists for this job on this track "
                f"(application_id={existing.id}, status={existing.status.value})."
            ),
        )

    application = app_repo.create_application(
        user_id=current_user.id,
        job_id=job_id,
        cv_track_id=track_id,
        notes=payload.notes,
        organization_id=current_user.organization_id,
    )

    doc_repo = DocumentRepository(current_user.db)
    for doc_type in (DocType.cv, DocType.cover_letter, DocType.screening_answer):
        doc = doc_repo.get_latest_document(track_id, doc_type, job_id=job_id)
        if doc is not None and doc.id is not None and doc.application_id is None:
            doc_repo.set_application_id(doc.id, application.id)

    return application


@router.get("/{track_id}/applications", response_model=list[ApplicationWithJob])
def list_applications_for_track(
    track_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ApplicationWithJob]:
    """All applications under this track, joined with job title/company/url
    -- same reasoning and pattern as list_matches_for_track in matches.py.
    """
    _get_owned_track(track_id, current_user)

    app_repo = ApplicationRepository(current_user.db)
    applications = app_repo.list_applications_for_track(track_id)
    # Lazy transition -- any 'queued' row whose undo window has closed
    # advances to 'ready_to_submit' right here, on read. No cron/background
    # job for this; see advance_expired_queued's docstring.
    applications = app_repo.advance_expired_queued(applications)

    job_repo = JobRepository(current_user.db)
    jobs_by_id = {
        job.id: job for job in job_repo.get_jobs_by_ids([a.job_id for a in applications])
    }

    results: list[ApplicationWithJob] = []
    for a in applications:
        job = jobs_by_id.get(a.job_id)
        if job is None or a.id is None:
            continue
        results.append(
            ApplicationWithJob(
                id=a.id,
                job_id=a.job_id,
                cv_track_id=a.cv_track_id,
                status=a.status,
                applied_at=a.applied_at,
                notes=a.notes,
                created_at=a.created_at,
                job_title=job.title,
                job_company=job.company,
                job_url=job.url,
                auto_applied=a.auto_applied,
                queued_at=a.queued_at,
                undo_deadline=a.undo_deadline,
                failure_reason=a.failure_reason,
            )
        )
    return results


@router.post(
    "/{track_id}/applications/{application_id}/cancel",
    response_model=Application,
)
def cancel_queued_application(
    track_id: UUID,
    application_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> Application:
    """Cancel an auto-applied application during its undo window. Only
    valid while status is still 'queued' -- once the window has closed
    (status is 'ready_to_submit' or later), there's nothing left to
    undo automatically; the candidate would need to withdraw manually
    via update_application_status instead, same as any other
    application at that point.
    """
    application = _get_owned_application(track_id, application_id, current_user)
    if application.status != ApplicationStatus.queued:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot cancel an application with status '{application.status.value}' "
                "-- only 'queued' applications (still inside their undo window) can be "
                "cancelled this way."
            ),
        )
    return ApplicationRepository(current_user.db).cancel_queued_application(application_id)


@router.patch(
    "/{track_id}/applications/{application_id}",
    response_model=Application,
)
def update_application_status(
    track_id: UUID,
    application_id: UUID,
    payload: UpdateApplicationStatusRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Application:
    """Move an application through its status lifecycle
    (draft -> submitted -> interviewing -> rejected/offer/withdrawn).
    applied_at is set automatically the first time status becomes
    'submitted' -- never accepted from the request body, so it can't be
    forged or backdated via the API.
    """
    _get_owned_application(track_id, application_id, current_user)
    return ApplicationRepository(current_user.db).update_status(
        application_id, status=payload.status, notes=payload.notes
    )
