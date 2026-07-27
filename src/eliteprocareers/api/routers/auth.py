from fastapi import APIRouter, HTTPException, status

from eliteprocareers.api.schemas import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
)
from eliteprocareers.db.auth import AuthError, sign_in, sign_up

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


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest) -> SignupResponse:
    """Create a new account. Added this session -- previously the only
    way to get a Supabase Auth user was via the dashboard/direct SQL
    (confirmed by grep: no signup path existed anywhere in this API
    before now), which meant nobody a founder invited to an org could
    ever actually join -- there was nowhere for them to create an
    account. Whether the response includes a usable session depends on
    this Supabase project's email-confirmation setting, which this code
    doesn't control -- both cases are handled explicitly, see
    SignupResponse.
    """
    try:
        result = sign_up(payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    user = result.get("user") or {}
    session = result.get("session")

    return SignupResponse(
        user_id=user.get("id", ""),
        email=user.get("email"),
        access_token=session.get("access_token") if session else None,
        refresh_token=session.get("refresh_token") if session else None,
        requires_confirmation=session is None,
    )
