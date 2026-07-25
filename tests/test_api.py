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
        f"/tracks/{FAKE_TRACK_ID}/documents/cv",
        f"/tracks/{FAKE_TRACK_ID}/documents/cv/latest",
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


FAKE_JOB_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.parametrize(
    "path,body",
    [
        (f"/tracks/{FAKE_TRACK_ID}/generate-cv", {"job_id": FAKE_JOB_ID}),
        (f"/tracks/{FAKE_TRACK_ID}/generate-cover-letter", {"job_id": FAKE_JOB_ID}),
        (
            f"/tracks/{FAKE_TRACK_ID}/generate-screening-answer",
            {"job_id": FAKE_JOB_ID, "question": "Why this role?"},
        ),
    ],
)
def test_generation_endpoints_require_auth(path, body):
    # Same reasoning as test_cv_upload_requires_auth -- POST endpoints
    # aren't covered by the parametrized GET-only 401 check above.
    r = client.post(path, json=body)
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


FAKE_DOC_ID = "44444444-4444-4444-4444-444444444444"


def _track_row(user_id=FAKE_USER_ID):
    return {
        "id": FAKE_TRACK_ID,
        "user_id": user_id,
        "track_name": "Product Management / SaaS",
        "target_roles": ["Product Manager"],
        "scoring_weights": {},
    }


def _profile_row():
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "user_id": FAKE_USER_ID,
        "full_name": "James Maina",
        "summary": "Experienced product manager.",
    }


def _job_row():
    return {
        "id": FAKE_JOB_ID,
        "source": "greenhouse",
        "external_id": "ext-1",
        "company": "Acme",
        "title": "Senior PM",
        "description": "Own the roadmap for a SaaS product.",
        "url": "https://example.com/job",
        "location": "Remote",
        "ingested_at": "2026-07-01T00:00:00Z",
    }


def _make_fake_request(job_present=True):
    """Builds a fake httpx.request()/httpx.get() handler covering every
    Supabase table hit by the generate-* pipeline: auth, cv_tracks,
    candidate_profiles + its empty related tables, jobs, and
    generated_documents (both the list_versions read inside
    create_document and the final insert).
    """
    empty_profile_tables = (
        "candidate_skills",
        "work_experience",
        "education",
        "certifications",
        "languages",
        "projects",
        "references",
        "achievements",
    )

    def handler(method, url, **kwargs):
        if url.endswith("/auth/v1/user"):
            return httpx.Response(
                200,
                json={"id": FAKE_USER_ID, "email": "james@example.com"},
                request=httpx.Request("GET", url),
            )
        if "/rest/v1/cv_tracks" in url:
            return httpx.Response(
                200, json=[_track_row()], request=httpx.Request(method, url)
            )
        if "/rest/v1/candidate_profiles" in url:
            return httpx.Response(
                200, json=[_profile_row()], request=httpx.Request(method, url)
            )
        if any(f"/rest/v1/{t}" in url for t in empty_profile_tables):
            return httpx.Response(200, json=[], request=httpx.Request(method, url))
        if "/rest/v1/jobs" in url:
            payload = [_job_row()] if job_present else []
            return httpx.Response(200, json=payload, request=httpx.Request(method, url))
        if "/rest/v1/generated_documents" in url:
            if method == "GET":
                # list_versions() inside create_document(), used to compute
                # the next version number -- empty means this is version 1.
                return httpx.Response(200, json=[], request=httpx.Request(method, url))
            if method == "POST":
                body = kwargs.get("json", {})
                saved = {
                    "id": FAKE_DOC_ID,
                    "user_id": FAKE_USER_ID,
                    "cv_track_id": FAKE_TRACK_ID,
                    "application_id": None,
                    "doc_type": body.get("doc_type"),
                    "content": body.get("content"),
                    "version": 1,
                    "ai_model_used": body.get("ai_model_used"),
                    "created_at": "2026-07-25T09:00:00Z",
                }
                return httpx.Response(
                    201, json=[saved], request=httpx.Request(method, url)
                )
        raise AssertionError(f"unexpected {method} {url}")

    return handler


def test_generate_cv_success(monkeypatch):
    fake_request = _make_fake_request()
    monkeypatch.setattr(httpx, "get", lambda url, **kw: fake_request("GET", url, **kw))
    monkeypatch.setattr(httpx, "request", fake_request)

    def fake_groq_post(url, **kwargs):
        assert url == "https://api.groq.com/openai/v1/chat/completions"
        cv_json = (
            '{"summary": "Tailored PM summary.", "skills": ["Roadmapping"], '
            '"work_experience": [], "education": [], "certifications": []}'
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": cv_json}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_groq_post)

    r = client.post(
        f"/tracks/{FAKE_TRACK_ID}/generate-cv",
        json={"job_id": FAKE_JOB_ID},
        headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["doc_type"] == "cv"
    assert body["cv_track_id"] == FAKE_TRACK_ID
    assert "Tailored PM summary." in body["content"]


def test_generate_cover_letter_success(monkeypatch):
    fake_request = _make_fake_request()
    monkeypatch.setattr(httpx, "get", lambda url, **kw: fake_request("GET", url, **kw))
    monkeypatch.setattr(httpx, "request", fake_request)

    def fake_groq_post(url, **kwargs):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Dear Hiring Manager,\n\n...\n\nSincerely,"}}
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_groq_post)

    r = client.post(
        f"/tracks/{FAKE_TRACK_ID}/generate-cover-letter",
        json={"job_id": FAKE_JOB_ID},
        headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["doc_type"] == "cover_letter"
    assert body["content"].startswith("Dear Hiring Manager,")


def test_generate_cv_job_not_found_returns_404(monkeypatch):
    fake_request = _make_fake_request(job_present=False)
    monkeypatch.setattr(httpx, "get", lambda url, **kw: fake_request("GET", url, **kw))
    monkeypatch.setattr(httpx, "request", fake_request)

    r = client.post(
        f"/tracks/{FAKE_TRACK_ID}/generate-cv",
        json={"job_id": FAKE_JOB_ID},
        headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
    )
    assert r.status_code == 404


def test_generate_cv_not_owned_track_returns_404(monkeypatch):
    other_user_id = "00000000-0000-0000-0000-000000000000"

    def handler(method, url, **kwargs):
        if url.endswith("/auth/v1/user"):
            return httpx.Response(
                200, json={"id": FAKE_USER_ID}, request=httpx.Request("GET", url)
            )
        if "/rest/v1/cv_tracks" in url:
            return httpx.Response(
                200,
                json=[_track_row(user_id=other_user_id)],
                request=httpx.Request(method, url),
            )
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(httpx, "get", lambda url, **kw: handler("GET", url, **kw))
    monkeypatch.setattr(httpx, "request", handler)

    r = client.post(
        f"/tracks/{FAKE_TRACK_ID}/generate-cv",
        json={"job_id": FAKE_JOB_ID},
        headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
    )
    assert r.status_code == 404
