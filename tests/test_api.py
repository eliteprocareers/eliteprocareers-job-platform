"""
Tests for the API layer (eliteprocareers.api). Supabase itself is mocked
at the httpx layer -- these tests check routing, auth enforcement, and
request/response shaping, not real Supabase behavior.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from eliteprocareers.api.main import app

client = TestClient(app)

FAKE_TOKEN = "fake.jwt.token"
FAKE_USER_ID = "43324cff-f36c-404a-bd6a-873bc6bfc050"
FAKE_TRACK_ID = "abff642a-99eb-41c3-a0a2-96739f3a2500"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


FAKE_UPLOAD_ID = "f499ad20-ee37-4a43-8a13-5eef00cfd43a"


@pytest.mark.parametrize(
    "path",
    [
        "/profile/me",
        "/tracks",
        f"/tracks/{FAKE_TRACK_ID}/matches",
        f"/profile/cv-upload-status/{FAKE_UPLOAD_ID}",
    ],
)
def test_protected_routes_require_auth(path):
    r = client.get(path)
    assert r.status_code == 401


def test_cv_upload_requires_auth():
    # POST, not GET, since /profile/cv-upload only accepts POST -- kept
    # as its own test rather than folded into the parametrized GET list
    # above.
    r = client.post("/profile/cv-upload", files={"file": ("cv.txt", b"x" * 200, "text/plain")})
    assert r.status_code == 401


def test_login_success(monkeypatch):
    def fake_post(url, **kwargs):
        assert url.endswith("/auth/v1/token")
        return httpx.Response(
            200,
            json={
                "access_token": FAKE_TOKEN,
                "refresh_token": "fake-refresh",
                "user": {"id": FAKE_USER_ID, "email": "james@example.com"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    r = client.post("/auth/login", json={"email": "james@example.com", "password": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] == FAKE_TOKEN
    assert body["user_id"] == FAKE_USER_ID


def test_login_bad_credentials(monkeypatch):
    def fake_post(url, **kwargs):
        return httpx.Response(
            400,
            json={"error_description": "Invalid login credentials"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    r = client.post("/auth/login", json={"email": "james@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_list_tracks_authenticated(monkeypatch):
    def fake_get(url, **kwargs):
        if url.endswith("/auth/v1/user"):
            return httpx.Response(
                200,
                json={"id": FAKE_USER_ID, "email": "james@example.com"},
                request=httpx.Request("GET", url),
            )
        if url.endswith("/rest/v1/cv_tracks"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": FAKE_TRACK_ID,
                        "user_id": FAKE_USER_ID,
                        "track_name": "Product Management / SaaS",
                        "target_roles": ["Product Manager"],
                        "scoring_weights": {},
                    }
                ],
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: fake_get(url, **kw))

    r = client.get("/tracks", headers={"Authorization": f"Bearer {FAKE_TOKEN}"})
    assert r.status_code == 200
    tracks = r.json()
    assert len(tracks) == 1
    assert tracks[0]["track_name"] == "Product Management / SaaS"


def test_get_track_not_owned_returns_404(monkeypatch):
    other_user_id = "00000000-0000-0000-0000-000000000000"

    def fake_get(url, **kwargs):
        if url.endswith("/auth/v1/user"):
            return httpx.Response(
                200, json={"id": FAKE_USER_ID}, request=httpx.Request("GET", url)
            )
        if "/rest/v1/cv_tracks" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": FAKE_TRACK_ID,
                        "user_id": other_user_id,
                        "track_name": "Someone else's track",
                        "target_roles": [],
                        "scoring_weights": {},
                    }
                ],
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: fake_get(url, **kw))
    monkeypatch.setattr(httpx, "get", fake_get)

    r = client.get(f"/tracks/{FAKE_TRACK_ID}", headers={"Authorization": f"Bearer {FAKE_TOKEN}"})
    assert r.status_code == 404
