"""
Supabase Auth helper — signs in/up a user with email/password and returns
their JWT access token, used to build a user-scoped, RLS-enforced client.

This is NOT the full Auth module (no session refresh, password reset,
etc. yet) — just enough to authenticate as a real user for backend
scripts, testing, and the invite-accept flow (added this session --
without a real signup path, an invited person with no existing account
had no way to ever accept an invite, which would make the whole invite
feature theoretical rather than usable).
"""

import httpx

from eliteprocareers.config import settings


class AuthError(Exception):
    """Raised when Supabase Auth returns an error (bad credentials, etc.)."""


def sign_up(email: str, password: str) -> dict:
    """Create a new Supabase Auth user. Returns dict with user and,
    IF the project has email confirmation disabled, a live session
    (access_token/refresh_token) -- otherwise session is null and the
    caller must confirm via email before signing in. The API layer
    (auth.py router) handles both cases explicitly rather than assuming
    one, since this depends on a Supabase project setting this codebase
    doesn't control from application code.

    Raises AuthError with the server's message on failure (e.g. email
    already registered, weak password).
    """
    url = f"{settings.supabase_url}/auth/v1/signup"
    response = httpx.post(
        url,
        headers={
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password},
        timeout=15,
    )

    if response.status_code != 200:
        detail = response.json().get("error_description") or response.json().get(
            "msg", response.text
        )
        raise AuthError(f"Sign-up failed ({response.status_code}): {detail}")

    return response.json()


def sign_in(email: str, password: str) -> dict:
    """Sign in with email/password. Returns dict with access_token, refresh_token, user.

    Raises AuthError with the server's message on failure.
    """
    url = f"{settings.supabase_url}/auth/v1/token"
    response = httpx.post(
        url,
        params={"grant_type": "password"},
        headers={
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password},
        timeout=15,
    )

    if response.status_code != 200:
        detail = response.json().get("error_description", response.text)
        raise AuthError(f"Sign-in failed ({response.status_code}): {detail}")

    return response.json()


def get_user(access_token: str) -> dict:
    """Resolve an access token to the Supabase Auth user it belongs to.

    Used by the API layer to turn an incoming `Authorization: Bearer <jwt>`
    header into a concrete user_id before constructing a user-scoped
    SupabaseClient for that request -- never trust a user_id supplied by
    the client itself; always derive it from the token via this call.
    """
    url = f"{settings.supabase_url}/auth/v1/user"
    response = httpx.get(
        url,
        headers={
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=15,
    )
    if response.status_code != 200:
        detail = response.json().get("msg", response.text)
        raise AuthError(f"Token validation failed ({response.status_code}): {detail}")
    return response.json()
