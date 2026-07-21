from fastapi import APIRouter, HTTPException, status

from eliteprocareers.api.schemas import LoginRequest, LoginResponse
from eliteprocareers.db.auth import AuthError, sign_in

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Exchange email/password for a Supabase access token. The returned
    access_token is what every other endpoint expects as a Bearer token.
    """
    try:
        session = sign_in(payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    return LoginResponse(
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        user_id=session["user"]["id"],
        email=session["user"].get("email"),
    )
