from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.routers.tracks import _get_owned_track
from eliteprocareers.api.schemas import DocumentsBundle, ScreeningAnswerRequest
from eliteprocareers.generation.cover_letter import generate_cover_letter
from eliteprocareers.generation.cv_tailoring import generate_tailored_cv
from eliteprocareers.generation.screening_answer import generate_screening_answer
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import DocType, GeneratedDocument
from eliteprocareers.profiles.repository import ProfileRepository

router = APIRouter(prefix="/tracks", tags=["documents"])


def _get_owned_job_with_match(track_id: UUID, job_id: UUID, current_user: CurrentUser):
    """Verify the track is owned by current_user, a match exists for
    (user, job, track), and the job itself exists. 404 in every failure
    case, same can't-enumerate-other-ids reasoning as the rest of this
    API. Returns (track, job).
    """
    track = _get_owned_track(track_id, current_user)

    match = UserJobMatchRepository(current_user.db).get_match(
        user_id=current_user.id, job_id=job_id, cv_track_id=track_id
    )
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No match found for this job under this track.",
        )

    jobs = JobRepository(current_user.db).get_jobs_by_ids([job_id])
    if not jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return track, jobs[0]


def _get_profile_or_400(current_user: CurrentUser):
    profile = ProfileRepository(current_user.db).get_full_profile(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No candidate profile found for this user -- upload a CV first.",
        )
    return profile


@router.post(
    "/{track_id}/jobs/{job_id}/generate-cv",
    response_model=GeneratedDocument,
    status_code=status.HTTP_201_CREATED,
)
def generate_cv_for_job(
    track_id: UUID,
    job_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    """Generate (or regenerate, as a new version) a tailored CV for this
    track+job pair. Requires an existing match and a completed profile.
    """
    track, job = _get_owned_job_with_match(track_id, job_id, current_user)
    profile = _get_profile_or_400(current_user)

    doc_repo = DocumentRepository(current_user.db)
    document = generate_tailored_cv(
        profile=profile,
        track=track,
        job_description=job.description or "",
        doc_repo=doc_repo,
        job_id=job_id,
    )
    return document


@router.post(
    "/{track_id}/jobs/{job_id}/generate-cover-letter",
    response_model=GeneratedDocument,
    status_code=status.HTTP_201_CREATED,
)
def generate_cover_letter_for_job(
    track_id: UUID,
    job_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    track, job = _get_owned_job_with_match(track_id, job_id, current_user)
    profile = _get_profile_or_400(current_user)

    doc_repo = DocumentRepository(current_user.db)
    document = generate_cover_letter(
        profile=profile,
        track=track,
        job_description=job.description or "",
        doc_repo=doc_repo,
        job_id=job_id,
    )
    return document


@router.post(
    "/{track_id}/jobs/{job_id}/generate-screening-answer",
    response_model=GeneratedDocument,
    status_code=status.HTTP_201_CREATED,
)
def generate_screening_answer_for_job(
    track_id: UUID,
    job_id: UUID,
    payload: ScreeningAnswerRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    track, job = _get_owned_job_with_match(track_id, job_id, current_user)
    profile = _get_profile_or_400(current_user)

    doc_repo = DocumentRepository(current_user.db)
    document = generate_screening_answer(
        profile=profile,
        track=track,
        job_description=job.description or "",
        question=payload.question,
        doc_repo=doc_repo,
        word_limit=payload.word_limit,
        job_id=job_id,
    )
    return document


@router.get("/{track_id}/jobs/{job_id}/documents", response_model=DocumentsBundle)
def get_documents_for_job(
    track_id: UUID,
    job_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentsBundle:
    """Latest generated CV / cover letter / screening answer for this
    track+job, whichever exist. All three fields are None on a job
    nothing has been generated for yet -- not a 404, since "no documents
    generated" is a normal, expected state.
    """
    _get_owned_job_with_match(track_id, job_id, current_user)

    doc_repo = DocumentRepository(current_user.db)
    return DocumentsBundle(
        cv=doc_repo.get_latest_document(track_id, DocType.cv, job_id=job_id),
        cover_letter=doc_repo.get_latest_document(track_id, DocType.cover_letter, job_id=job_id),
        screening_answer=doc_repo.get_latest_document(
            track_id, DocType.screening_answer, job_id=job_id
        ),
    )
