"""
Thin PostgREST client — raw HTTP via httpx, no Supabase JS client, no ORM.

Two modes:
  - User-scoped (default): authenticated as a real user via their JWT.
    RLS applies exactly as it would for that user in production.
  - Admin (service_role): bypasses RLS entirely. Reserved for trusted
    server-side jobs — scheduled ingestion, maintenance, migrations.
    Never expose the service_role key to anything client-facing.

Usage (user-scoped, the default for anything acting on behalf of a person):
    from eliteprocareers.db.auth import sign_in
    from eliteprocareers.db.client import SupabaseClient

    session = sign_in("jamesmaina263@gmail.com", "...")
    db = SupabaseClient(access_token=session["access_token"])
    profiles = db.select("candidate_profiles")

Usage (admin, only for backend jobs — e.g. job ingestion writing to `jobs`):
    db = SupabaseClient(use_service_role=True)
    db.insert("jobs", {...})
"""

from typing import Any

import httpx
import time

from eliteprocareers.config import settings


class SupabaseError(Exception):
    """Raised when PostgREST returns a non-2xx response."""


class SupabaseClient:
    def __init__(self, access_token: str | None = None, use_service_role: bool = False):
        if use_service_role and access_token:
            raise ValueError("Pass either access_token or use_service_role=True, not both.")
        if not use_service_role and not access_token:
            raise ValueError(
                "User-scoped client requires access_token. "
                "Pass use_service_role=True explicitly for admin access."
            )

        self.base_url = f"{settings.supabase_url}/rest/v1"

        if use_service_role:
            bearer = settings.supabase_service_role_key
            apikey = settings.supabase_service_role_key
        else:
            bearer = access_token
            apikey = settings.supabase_anon_key

        self._headers = {
            "apikey": apikey,
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = httpx.request(
            method,
            f"{self.base_url}/{path}",
            headers=self._headers,
            timeout=15,
            **kwargs,
        )
        if response.status_code >= 400:
            raise SupabaseError(
                f"{method} {path} failed ({response.status_code}): {response.text}"
            )
        return response

    def select(self, table: str, params: dict | None = None) -> list[dict]:
        """GET rows. params supports PostgREST query syntax, e.g. {'select': '*', 'id': 'eq.123'}."""
        response = self._request("GET", table, params=params or {"select": "*"})
        return response.json()

    def insert(self, table: str, data: dict | list[dict]) -> list[dict]:
        """POST new row(s). Returns the inserted row(s) (Prefer: return=representation).

        Retries up to 3 times on transient network failures (httpx.TransportError
        and subclasses — connection drops, TLS record errors, etc., a known flaky
        pattern on WSL2's networking stack). Does NOT retry on real HTTP error
        responses (4xx/5xx) — those raise SupabaseError immediately as before.
        """
        headers = {**self._headers, "Prefer": "return=representation"}
        url = f"{self.base_url}/{table}"

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.post(url, headers=headers, json=data, timeout=15)
            except httpx.TransportError as e:
                last_error = e
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, then 2s
                    continue
                raise SupabaseError(
                    f"INSERT {table} failed after 3 attempts due to network errors: {e}"
                ) from e

            if response.status_code >= 400:
                raise SupabaseError(f"INSERT {table} failed ({response.status_code}): {response.text}")
            return response.json()

        raise SupabaseError(f"INSERT {table} failed after 3 attempts: {last_error}")

    def update(self, table: str, data: dict, params: dict) -> list[dict]:
        """PATCH matching rows. params must include a filter, e.g. {'id': 'eq.123'}."""
        headers = {**self._headers, "Prefer": "return=representation"}
        response = httpx.patch(
            f"{self.base_url}/{table}", headers=headers, params=params, json=data, timeout=15
        )
        if response.status_code >= 400:
            raise SupabaseError(f"UPDATE {table} failed ({response.status_code}): {response.text}")
        return response.json()

    def delete(self, table: str, params: dict) -> list[dict]:
        """DELETE matching rows. params must include a filter, e.g. {'id': 'eq.123'}."""
        headers = {**self._headers, "Prefer": "return=representation"}
        response = httpx.delete(
            f"{self.base_url}/{table}", headers=headers, params=params, timeout=15
        )
        if response.status_code >= 400:
            raise SupabaseError(f"DELETE {table} failed ({response.status_code}): {response.text}")
        return response.json()
