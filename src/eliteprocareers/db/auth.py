"""
Supabase Auth helper — signs in a user with email/password and returns
their JWT access token, used to build a user-scoped, RLS-enforced client.

This is NOT the full Auth module (no signup flow, session refresh, etc.
yet) — just enough to authenticate as a real user for backend scripts
and testing.
"""

import httpx

from eliteprocareers.config import settings


class AuthError(Exception):
    """Raised when Supabase Auth returns an error (bad credentials, etc.)."""


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
