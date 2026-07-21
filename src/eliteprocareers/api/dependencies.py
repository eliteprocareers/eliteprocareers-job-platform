"""
Shared FastAPI dependencies for authentication and DB access.

Design rule, load-bearing for RLS correctness: every request handler that
acts on a specific user's data must go through get_current_user() to obtain
a user-scoped SupabaseClient (access_token path) -- never use_service_role
for anything triggered by an incoming request. service_role stays reserved
for backend jobs (ingestion, matching runs), exactly as matching_service.py's
docstring already warns. This mirrors the same RLS boundary
matching/repository.py and jobs/repository.py were built around.

The user_id used anywhere in a request handler must always come from the
resolved token (CurrentUser.id below), never from a path or query param --
a client could otherwise pass an arbitrary user_id and read someone else's
data. RLS would still block writes/selects on other tables, but handlers
must not even construct filters against an unverified id.
"""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from eliteprocareers.db.auth import AuthError, get_user
from eliteprocareers.db.client import SupabaseClient

_bearer_scheme = HTTPBearer(
    scheme_name="SupabaseJWT",
    description="Supabase Auth access token, obtained from POST /auth/login",
)


@dataclass
class CurrentUser:
    id: UUID
    email: str | None
    access_token: str
    db: SupabaseClient


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> CurrentUser:
    """Validate the bearer token against Supabase Auth and return a
    CurrentUser bundling the verified user id with a ready-to-use,
    user-scoped SupabaseClient for the rest of the request.
    """
    token = credentials.credentials
    try:
        user = get_user(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        id=UUID(user["id"]),
        email=user.get("email"),
        access_token=token,
        db=SupabaseClient(access_token=token),
    )
