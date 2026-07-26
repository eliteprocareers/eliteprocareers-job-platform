"""
Unit tests for ApplicationRepository. SupabaseClient is mocked directly
(unittest.mock.Mock(spec=...)) rather than at the httpx layer -- this
repository has one piece of real logic worth isolating (applied_at is
set server-side, exactly once, only on the first transition to
'submitted' -- see update_status()'s docstring), and that's easiest to
pin down by asserting on the exact payload passed to db.update(), not
by round-tripping through the API layer every time.

Router-level coverage (auth, ownership, request/response shaping) for
the applications endpoints lives in test_api.py, following the same
pattern as the rest of that file.
"""
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.application_repository import ApplicationRepository
from eliteprocareers.profiles.models import Application, ApplicationStatus

USER_ID = UUID("43324cff-f36c-404a-bd6a-873bc6bfc050")
JOB_ID = UUID("11111111-1111-1111-1111-111111111111")
TRACK_ID = UUID("abff642a-99eb-41c3-a0a2-96739f3a2500")
APPLICATION_ID = UUID("802be1b8-7e78-42de-9602-d114e7976c49")


def _application_row(**overrides) -> dict:
    row = {
        "id": str(APPLICATION_ID),
        "user_id": str(USER_ID),
        "job_id": str(JOB_ID),
        "cv_track_id": str(TRACK_ID),
        "status": ApplicationStatus.draft.value,
        "applied_at": None,
        "notes": None,
        "created_at": "2026-07-26T00:00:00Z",
        "updated_at": "2026-07-26T00:00:00Z",
    }
    row.update(overrides)
    return row


def _repo() -> tuple[ApplicationRepository, Mock]:
    db = Mock(spec=SupabaseClient)
    return ApplicationRepository(db), db


def test_create_application_defaults_to_draft_status():
    repo, db = _repo()
    db.insert.return_value = [_application_row()]

    result = repo.create_application(user_id=USER_ID, job_id=JOB_ID, cv_track_id=TRACK_ID)

    assert isinstance(result, Application)
    assert result.status == ApplicationStatus.draft
    payload = db.insert.call_args.args[1]
    assert payload["status"] == ApplicationStatus.draft.value
    assert payload["user_id"] == str(USER_ID)
    assert payload["job_id"] == str(JOB_ID)
    assert payload["cv_track_id"] == str(TRACK_ID)


def test_create_application_passes_notes_through():
    repo, db = _repo()
    db.insert.return_value = [_application_row(notes="Referred by a friend.")]

    result = repo.create_application(
        user_id=USER_ID, job_id=JOB_ID, cv_track_id=TRACK_ID, notes="Referred by a friend."
    )

    assert result.notes == "Referred by a friend."
    payload = db.insert.call_args.args[1]
    assert payload["notes"] == "Referred by a friend."


def test_get_application_returns_none_when_not_found():
    repo, db = _repo()
    db.select.return_value = []

    assert repo.get_application(APPLICATION_ID) is None


def test_get_application_returns_parsed_application():
    repo, db = _repo()
    db.select.return_value = [_application_row(status=ApplicationStatus.submitted.value)]

    result = repo.get_application(APPLICATION_ID)

    assert result is not None
    assert result.id == APPLICATION_ID
    assert result.status == ApplicationStatus.submitted


def test_list_applications_for_track_orders_newest_first():
    repo, db = _repo()
    db.select.return_value = [_application_row(), _application_row(id=str(JOB_ID))]

    results = repo.list_applications_for_track(TRACK_ID)

    assert len(results) == 2
    params = db.select.call_args.kwargs["params"]
    assert params["cv_track_id"] == f"eq.{TRACK_ID}"
    assert params["order"] == "created_at.desc"


def test_update_status_to_submitted_sets_applied_at_first_time():
    repo, db = _repo()
    # get_application() (called internally to check the current applied_at)
    # returns a draft row with no applied_at yet.
    db.select.return_value = [_application_row(applied_at=None)]
    db.update.return_value = [
        _application_row(status=ApplicationStatus.submitted.value, applied_at="2026-07-26T10:00:00Z")
    ]

    result = repo.update_status(APPLICATION_ID, status=ApplicationStatus.submitted)

    assert result.status == ApplicationStatus.submitted
    update_data = db.update.call_args.kwargs["data"]
    assert update_data["status"] == ApplicationStatus.submitted.value
    assert "applied_at" in update_data
    # Set server-side to "now" -- just check it's a real, parseable, recent
    # UTC timestamp, not a fixed string the caller could have forged.
    parsed = datetime.fromisoformat(update_data["applied_at"])
    assert (datetime.now(timezone.utc) - parsed).total_seconds() < 30


def test_update_status_to_submitted_does_not_overwrite_existing_applied_at():
    repo, db = _repo()
    # Already has an applied_at from an earlier submit -- e.g. a
    # submitted -> rejected -> submitted round trip. Re-submitting must
    # not backdate/refresh it.
    db.select.return_value = [
        _application_row(status=ApplicationStatus.rejected.value, applied_at="2026-07-01T00:00:00Z")
    ]
    db.update.return_value = [_application_row(status=ApplicationStatus.submitted.value)]

    repo.update_status(APPLICATION_ID, status=ApplicationStatus.submitted)

    update_data = db.update.call_args.kwargs["data"]
    assert "applied_at" not in update_data


def test_update_status_non_submitted_never_touches_applied_at():
    repo, db = _repo()
    db.update.return_value = [_application_row(status=ApplicationStatus.interviewing.value)]

    repo.update_status(APPLICATION_ID, status=ApplicationStatus.interviewing)

    # Moving to a non-'submitted' status shouldn't even need to look up
    # the current row -- get_application() (db.select) is never called.
    db.select.assert_not_called()
    update_data = db.update.call_args.kwargs["data"]
    assert "applied_at" not in update_data
    assert update_data["status"] == ApplicationStatus.interviewing.value


def test_update_status_passes_notes_when_provided():
    repo, db = _repo()
    db.update.return_value = [_application_row(notes="Second round scheduled.")]

    repo.update_status(
        APPLICATION_ID, status=ApplicationStatus.interviewing, notes="Second round scheduled."
    )

    update_data = db.update.call_args.kwargs["data"]
    assert update_data["notes"] == "Second round scheduled."


def test_update_status_omits_notes_key_when_not_provided():
    repo, db = _repo()
    db.update.return_value = [_application_row()]

    repo.update_status(APPLICATION_ID, status=ApplicationStatus.interviewing)

    update_data = db.update.call_args.kwargs["data"]
    assert "notes" not in update_data
