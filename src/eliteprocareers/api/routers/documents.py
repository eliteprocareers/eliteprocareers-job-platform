from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.routers.tracks import _get_owned_track
from eliteprocareers.api.schemas import (
    GenerateCoverLetterRequest,
    GenerateCVRequest,
    GenerateScreeningAnswerRequest,
)
from eliteprocareers.generation.cover_letter import generate_cover_letter
from eliteprocareers.generation.cv_tailoring import CVGenerationError, generate_tailored_cv
from eliteprocareers.generation.screening_answer import generate_screening_answer
from eliteprocareers.jobs.repository import JobRepository
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import CVTrack, DocType, FullProfile, GeneratedDocument
from eliteprocareers.profiles.repository import ProfileRepository

router = APIRouter(prefix="/tracks", tags=["documents"])

# Stage 3/4 wiring (v26 §1d/§18): cv_tailoring.py, cover_letter.py, and
# screening_answer.py already existed as real, functional pipelines --
# confirmed exercised against real data (5 CVs, 1 cover letter in
# generated_documents as of v26) -- but had no API endpoint calling them.
# This router is that endpoint layer, following the same "thin HTTP layer
# over existing service/repository modules" rule main.py's docstring
# states for every other router here.
#
# Unlike CV upload (profile.py) and matching (tracks.py), these endpoints
# run synchronously rather than trigger+poll. Both of those background-task
# cases are either a genuine multi-minute loop (matching, over ~3000 jobs)
# or benefit from a client-visible upload_id before any processing starts.
# Generation here is a single Groq call producing one document -- a few
# seconds in the common case -- and DocumentRepository has no concept of a
# "pending" row to poll against (create_document() only ever inserts a
# finished document). generate_text()'s own retry logic (llm_client.py)
# can stretch a single call to multiple minutes under sustained 429s in
# the worst case; that's an accepted tradeoff for now given Vercel fluid
# compute is enabled (vercel.json), not a deliberate design decision to
# revisit if it proves to be a real problem in practice -- flagged as
# technical debt in the handover, not fixed here.


def _get_profile_and_job(
    track_id: UUID, job_id: UUID, current_user: CurrentUser
) -> tuple[CVTrack, FullProfile, str]:
    """Shared setup for all three generation endpoints: verify track
    ownership, load the candidate's real profile, and fetch the target
    job's description. Raises 404 if the track isn't owned, the profile
    doesn't exist yet, or the job_id doesn't resolve -- mirrors the
    existing 404-for-missing-or-not-owned pattern from tracks.py.
    """
    track = _get_owned_track(track_id, current_user)

    profile = ProfileRepository(current_user.db).get_full_profile(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidate profile exists yet for this user.",
        )

    jobs = JobRepository(current_user.db).get_jobs_by_ids([job_id])
    if not jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return track, profile, jobs[0].description or ""


@router.post(
    "/{track_id}/generate-cv",
    response_model=GeneratedDocument,
    status_code=status.HTTP_201_CREATED,
)
def generate_cv(
    track_id: UUID,
    payload: GenerateCVRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    """Stage 3 entry point: generate a tailored CV for this track against
    a specific job, and save it as a new generated_documents version.
    """
    track, profile, job_description = _get_profile_and_job(
        track_id, payload.job_id, current_user
    )
    doc_repo = DocumentRepository(current_user.db)
    try:
        return generate_tailored_cv(profile, track, job_description, doc_repo)
    except CVGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CV generation failed: {e}",
        ) from e


@router.post(
    "/{track_id}/generate-cover-letter",
    response_model=GeneratedDocument,
    status_code=status.HTTP_201_CREATED,
)
def generate_cover_letter_endpoint(
    track_id: UUID,
    payload: GenerateCoverLetterRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    """Stage 4 entry point: generate a cover letter for this track against
    a specific job, and save it as a new generated_documents version.
    """
    track, profile, job_description = _get_profile_and_job(
        track_id, payload.job_id, current_user
    )
    doc_repo = DocumentRepository(current_user.db)
    return generate_cover_letter(profile, track, job_description, doc_repo)


@router.post(
    "/{track_id}/generate-screening-answer",
    response_model=GeneratedDocument,
    status_code=status.HTTP_201_CREATED,
)
def generate_screening_answer_endpoint(
    track_id: UUID,
    payload: GenerateScreeningAnswerRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    """Generates an answer to a single application screening question for
    this track against a specific job, and saves it as a new
    generated_documents version. Not one of the original 5 stages by
    itself, but the same generation family (screening_answer.py) v26 §1d
    flagged as already-exercised-but-unwired alongside cover_letter.py.
    """
    track, profile, job_description = _get_profile_and_job(
        track_id, payload.job_id, current_user
    )
    doc_repo = DocumentRepository(current_user.db)
    return generate_screening_answer(
        profile, track, job_description, payload.question, doc_repo, payload.word_limit
    )


@router.get(
    "/{track_id}/documents/{doc_type}",
    response_model=list[GeneratedDocument],
)
def list_documents(
    track_id: UUID,
    doc_type: DocType,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[GeneratedDocument]:
    """All saved versions of a given document type for this track,
    oldest first (DocumentRepository.list_versions's own ordering).

    Known pre-existing limitation, not introduced by this endpoint:
    version numbers increment per (track, doc_type) regardless of which
    job or screening question a given version was generated for -- so a
    track with screening answers to two different questions shares one
    version sequence between them. Not fixed here; flagged as technical
    debt in the handover.
    """
    _get_owned_track(track_id, current_user)
    return DocumentRepository(current_user.db).list_versions(track_id, doc_type)


@router.get(
    "/{track_id}/documents/{doc_type}/latest",
    response_model=GeneratedDocument,
)
def get_latest_document(
    track_id: UUID,
    doc_type: DocType,
    current_user: CurrentUser = Depends(get_current_user),
) -> GeneratedDocument:
    """The most recent saved version of a given document type for this
    track. 404 if none has ever been generated.
    """
    _get_owned_track(track_id, current_user)
    doc = DocumentRepository(current_user.db).get_latest_document(track_id, doc_type)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No document of this type exists yet for this track.",
        )
    return doc
