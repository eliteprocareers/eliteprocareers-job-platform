"""
Unit tests for MatchingRunRepository.get_running_run_for_track(), focused
on the stale-run reaping logic added 2026-08-06. SupabaseClient is mocked
directly (unittest.mock.Mock(spec=...)), same pattern as
test_application_repository.py.

Context: production had matching_runs rows stuck at status='running'
indefinitely -- confirmed via Vercel:get_runtime_errors as function-
duration SIGTERM kills mid-run, which bypass run_matching_for_track_
tracked's except block entirely (mark_failed() never runs), leaving the
row orphaned and get_running_run_for_track's 409-conflict check blocking
every future retry forever. These tests pin down the fix: a 'running'
row older than STALE_RUN_SECONDS is auto-marked 'failed' and treated as
not-running, while a genuinely recent 'running' row still blocks a
second concurrent run as before.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.matching.repository import MatchingRunRepository

TRACK_ID = UUID("b341d141-5e3f-413e-8391-ff394ad85883")
USER_ID = UUID("be26c359-bcc4-459f-ac1b-b845a307e4d8")
ORG_ID = UUID("cc463b02-d405-4511-a48f-7f15fa498231")
RUN_ID = UUID("dbe546f3-9748-4a84-91ff-0aeb0c8cd6d0")


def _running_row(started_at: datetime, **overrides) -> dict:
    row = {
        "id": str(RUN_ID),
        "user_id": str(USER_ID),
        "cv_track_id": str(TRACK_ID),
        "organization_id": str(ORG_ID),
        "status": "running",
        "jobs_total": 6901,
        "jobs_processed": 3950,
        "error_message": None,
        "started_at": started_at.isoformat(),
    }
    row.update(overrides)
    return row


def _repo() -> tuple[MatchingRunRepository, Mock]:
    db = Mock(spec=SupabaseClient)
    return MatchingRunRepository(db), db


def test_recent_running_run_still_blocks_a_second_run():
    """A 'running' row from a few minutes ago is real -- unchanged
    behavior from before this fix."""
    repo, db = _repo()
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.select.return_value = [_running_row(started)]

    run = repo.get_running_run_for_track(TRACK_ID)

    assert run is not None
    assert run.id == RUN_ID
    db.update.assert_not_called()


def test_stale_running_run_is_reaped_and_treated_as_not_running():
    """A 'running' row older than STALE_RUN_SECONDS (1200s) is almost
    certainly an orphan from a killed background task -- reap it (mark
    failed) and let the caller start a fresh run instead of hitting a
    permanent 409."""
    repo, db = _repo()
    started = datetime.now(timezone.utc) - timedelta(seconds=1201)
    db.select.return_value = [_running_row(started)]

    run = repo.get_running_run_for_track(TRACK_ID)

    assert run is None
    db.update.assert_called_once()
    (table, payload), kwargs = db.update.call_args
    assert table == "matching_runs"
    assert payload["status"] == "failed"
    assert "3950/6901" in payload["error_message"]
    assert kwargs["params"] == {"id": f"eq.{RUN_ID}"}


def test_run_just_under_the_staleness_threshold_still_blocks():
    """Boundary check: just under STALE_RUN_SECONDS is still 'running',
    not reaped -- avoids reaping a genuinely in-flight run that's using
    most of its 800s maxDuration budget."""
    repo, db = _repo()
    started = datetime.now(timezone.utc) - timedelta(seconds=1199)
    db.select.return_value = [_running_row(started)]

    run = repo.get_running_run_for_track(TRACK_ID)

    assert run is not None
    db.update.assert_not_called()


def test_no_running_run_returns_none():
    repo, db = _repo()
    db.select.return_value = []

    run = repo.get_running_run_for_track(TRACK_ID)

    assert run is None
    db.update.assert_not_called()
