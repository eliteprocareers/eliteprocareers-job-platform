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

    def _request(self, method: str, path: str, headers: dict | None = None, **kwargs) -> httpx.Response:
        """Every DB call funnels through here. Retries up to 3 times on
        transient network failures (httpx.TransportError and subclasses --
        connection drops, TLS record-layer errors, read timeouts -- a known
        flaky pattern on WSL2's networking stack, confirmed live 2026-07-20
        when a ~27-minute matching run left a stale connection that then
        failed with SSL RECORD_LAYER_FAILURE, then ReadTimeout, on the very
        next call). Does NOT retry on real HTTP error responses (4xx/5xx) --
        those raise SupabaseError immediately, no retry, same as before.

        This retry logic previously existed only in insert() (added in an
        earlier session) -- select()/update()/delete() had none, which is
        exactly what crashed live during Stage-1 matching runs. Consolidated
        here so every method gets it, instead of each one duplicating its
        own copy.
        """
        request_headers = {**self._headers, **(headers or {})}
        url = f"{self.base_url}/{path}"

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.request(method, url, headers=request_headers, timeout=15, **kwargs)
            except httpx.TransportError as e:
                last_error = e
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, then 2s
                    continue
                raise SupabaseError(
                    f"{method} {path} failed after 3 attempts due to network errors: {e}"
                ) from e
            else:
                if response.status_code >= 400:
                    raise SupabaseError(
                        f"{method} {path} failed ({response.status_code}): {response.text}"
                    )
                return response

        raise SupabaseError(f"{method} {path} failed after 3 attempts: {last_error}")

    def select(self, table: str, params: dict | None = None) -> list[dict]:
        """GET rows. params supports PostgREST query syntax, e.g. {'select': '*', 'id': 'eq.123'}."""
        response = self._request("GET", table, params=params or {"select": "*"})
        return response.json()

    def insert(self, table: str, data: dict | list[dict]) -> list[dict]:
        """POST new row(s). Returns the inserted row(s) (Prefer: return=representation)."""
        response = self._request(
            "POST", table, headers={"Prefer": "return=representation"}, json=data
        )
        return response.json()

    def update(self, table: str, data: dict, params: dict) -> list[dict]:
        """PATCH matching rows. params must include a filter, e.g. {'id': 'eq.123'}."""
        response = self._request(
            "PATCH", table, headers={"Prefer": "return=representation"}, params=params, json=data
        )
        return response.json()

    def delete(self, table: str, params: dict) -> list[dict]:
        """DELETE matching rows. params must include a filter, e.g. {'id': 'eq.123'}."""
        response = self._request(
            "DELETE", table, headers={"Prefer": "return=representation"}, params=params
        )
        return response.json()

    def rpc(self, function_name: str, params: dict | None = None) -> Any:
        """Call a Postgres function via PostgREST's /rpc/{function_name}.

        Used for operations that must be atomic across more than one
        table (e.g. accept_organization_invite claiming an invite and
        inserting a membership row in one transaction) -- the same
        class of bug this project has hit twice already (profiles/
        repository.py's pre-fix blind inserts) from doing multi-step
        writes as separate REST calls with no transaction wrapping them.

        SECURITY DEFINER functions run with the *function's* privileges,
        not the caller's, but auth.uid()/auth.jwt() inside the function
        body still resolve from whichever token this client was built
        with -- so calling with a user-scoped client (the normal case)
        still ties the operation to that specific user, it just also
        gets to bypass RLS policies the function itself doesn't need.
        """
        response = self._request("POST", f"rpc/{function_name}", json=params or {})
        return response.json()
