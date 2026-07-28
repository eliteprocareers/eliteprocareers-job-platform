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
    organization_id: UUID | None
    organization_role: str | None
    """One of 'owner'/'admin'/'manager'/'staff' (migration 0014), or
    None if organization_id is also None. Resolved once here so every
    router can call organizations/permissions.py's has_permission()/
    require_permission() against it directly, instead of each router
    re-fetching the caller's own membership row to find their role --
    which is exactly the duplicated pattern _require_admin_role and
    _require_owner_role in api/routers/organizations.py had before
    this, now centralized.
    """


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

    db = SupabaseClient(access_token=token)

    # Multi-tenant orgs (added 2026-07-26): most tables now carry an RLS
    # policy requiring organization_id to match one of the caller's
    # memberships (is_org_member(...)). Resolved once per request here so
    # every repository insert downstream can use it, rather than each one
    # re-querying or guessing -- added when generate-cv / create_application
    # were found failing with 403 "new row violates row-level security
    # policy" because organization_id was never being set on new rows.
    #
    # role resolved in the same query (added with the 4-tier RBAC system,
    # migration 0014) for the same reason -- one source of truth per
    # request, not a re-fetch in every router that needs to know who's
    # allowed to do what.
    org_rows = db.select(
        "organization_members",
        params={"select": "organization_id,role", "user_id": f"eq.{user['id']}", "limit": "1"},
    )
    organization_id = UUID(org_rows[0]["organization_id"]) if org_rows else None
    organization_role = org_rows[0]["role"] if org_rows else None

    return CurrentUser(
        id=UUID(user["id"]),
        email=user.get("email"),
        access_token=token,
        db=db,
        organization_id=organization_id,
        organization_role=organization_role,
    )
