from fastapi import APIRouter, Depends, HTTPException, status

from eliteprocareers.api.dependencies import CurrentUser, get_current_user
from eliteprocareers.profiles.models import FullProfile
from eliteprocareers.profiles.repository import ProfileRepository

router = APIRouter(prefix="/profile", tags=["profile"])


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
