from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.api.schemas import CVUploadTriggerResponse
from eliteprocareers.parsing.document_extraction import SUPPORTED_EXTENSIONS
from eliteprocareers.parsing.pipeline import parse_cv_upload_tracked
from eliteprocareers.profiles.models import CVUpload, FullProfile
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.upload_repository import CVUploadRepository

router = APIRouter(prefix="/profile", tags=["profile"])

# Vercel's serverless functions have a request body size limit well
# below this in practice, but this is the app-level guard regardless --
# a CV is text-heavy, not media; 10MB is generous even for a
# multi-page PDF with embedded fonts/images.
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024


@router.get("/me", response_model=FullProfile)
def get_my_profile(current_user: CurrentUser = Depends(get_current_user)) -> FullProfile:
    """The authenticated user's full profile: base profile + skills, work
    experience, education, certifications, languages, projects,
    achievements, references -- everything get_full_profile() assembles.
    """
    repo = ProfileRepository(current_user.db)
    profile = repo.get_full_profile(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidate profile exists yet for this user.",
        )
    return profile


@router.post(
    "/cv-upload",
    response_model=CVUploadTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_cv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> CVUploadTriggerResponse:
    """Stage 1 (CV upload/parse) entrypoint. Accepts a PDF/DOCX/TXT file,
    kicks off text extraction + LLM parsing in the background, and
    returns immediately (202, not 200) -- extraction plus an LLM call
    takes a few real seconds, the same reasoning as trigger_matching()
    in tracks.py returning 202 rather than blocking on a multi-minute
    run. Creates a cv_uploads row synchronously (before returning) so
    the client always gets a real upload_id to poll. Poll
    GET /profile/cv-upload-status/{upload_id} for real completion
    status, same shape as GET /tracks/{id}/match-status/{run_id}.
    """
    if not file.filename or not file.filename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Supported: {', '.join(SUPPORTED_EXTENSIONS)}.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
        )
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB limit.",
        )

    upload = CVUploadRepository(current_user.db).create_upload(
        user_id=current_user.id,
        filename=file.filename,
        file_size_bytes=len(content),
    )
    background_tasks.add_task(
        parse_cv_upload_tracked,
        current_user.id,
        upload.id,
        file.filename,
        content,
        current_user.db,
    )
    return CVUploadTriggerResponse(
        upload_id=upload.id,
        filename=file.filename,
        status="processing",
        message=(
            "CV upload received. Parsing started in the background. "
            "Poll GET /profile/cv-upload-status/{upload_id} for real "
            "completion status."
        ),
    )


@router.get("/cv-upload-status/{upload_id}", response_model=CVUpload)
def get_cv_upload_status(
    upload_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> CVUpload:
    """Poll endpoint for a CV upload/parse job's real status --
    processing, completed, or failed. Ownership is checked against
    current_user.id (never a path/query param) per dependencies.py's
    standing rule; returns 404 for both "doesn't exist" and "exists but
    belongs to someone else", same can't-enumerate-other-users'-ids
    reasoning as tracks.py's get_match_status.
    """
    upload = CVUploadRepository(current_user.db).get_upload(upload_id)
    if upload is None or upload.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="CV upload not found."
        )
    return upload
