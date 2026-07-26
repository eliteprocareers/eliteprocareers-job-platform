"""
Unit tests for eliteprocareers.matching.auto_apply.maybe_auto_apply.

Pure logic tests -- everything below it (ApplicationRepository,
DocumentRepository, CoverLetterStyleSampleRepository, the generation
functions) is mocked, since this function's own job is orchestration/
branching, not I/O. Real end-to-end coverage against a live DB is a
separate concern (same sandbox limitation as tests/test_api.py: no
real pytest run here, this is syntax/logic-checked only, needs running
for real on a machine with disk space for the torch/sentence-
transformers install).
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from eliteprocareers.jobs.models import Job
from eliteprocareers.profiles.models import Application, ApplicationStatus, CVTrack, FullProfile


def _fake_track(**overrides) -> CVTrack:
    defaults = dict(
        id=uuid4(),
        user_id=uuid4(),
        track_name="Test Track",
        auto_apply_enabled=True,
        auto_apply_min_score=0.85,
        undo_window_minutes=15,
    )
    defaults.update(overrides)
    return CVTrack(**defaults)


def _fake_job(**overrides) -> Job:
    defaults = dict(
        id=uuid4(),
        source="greenhouse",
        external_id="ext-123",
        company="Acme Corp",
        title="Product Manager",
        description="A great job.",
        ingested_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)


def _fake_profile() -> FullProfile:
    # FullProfile's exact required sub-fields aren't relevant to
    # maybe_auto_apply's own branching (it just passes profile through
    # to generate_tailored_cv/generate_cover_letter, both mocked here),
    # so a minimally-valid instance is enough.
    return MagicMock(spec=FullProfile)


@patch("eliteprocareers.matching.auto_apply.generate_cover_letter")
@patch("eliteprocareers.matching.auto_apply.generate_tailored_cv")
@patch("eliteprocareers.matching.auto_apply.CoverLetterStyleSampleRepository")
@patch("eliteprocareers.matching.auto_apply.DocumentRepository")
@patch("eliteprocareers.matching.auto_apply.ApplicationRepository")
def test_auto_apply_disabled_track_does_nothing(
    mock_app_repo_cls, mock_doc_repo_cls, mock_sample_repo_cls, mock_gen_cv, mock_gen_cl
):
    from eliteprocareers.matching.auto_apply import maybe_auto_apply

    track = _fake_track(auto_apply_enabled=False)
    result = maybe_auto_apply(
        db=MagicMock(), user_id=uuid4(), track=track, job=_fake_job(),
        match_score=0.99, full_profile=_fake_profile(),
    )
    assert result is False
    mock_app_repo_cls.assert_not_called()


@patch("eliteprocareers.matching.auto_apply.generate_cover_letter")
@patch("eliteprocareers.matching.auto_apply.generate_tailored_cv")
@patch("eliteprocareers.matching.auto_apply.CoverLetterStyleSampleRepository")
@patch("eliteprocareers.matching.auto_apply.DocumentRepository")
@patch("eliteprocareers.matching.auto_apply.ApplicationRepository")
def test_auto_apply_manual_approval_only_track_does_nothing(
    mock_app_repo_cls, mock_doc_repo_cls, mock_sample_repo_cls, mock_gen_cv, mock_gen_cl
):
    # undo_window_minutes=None means manual-approval-only -- auto_apply_
    # enabled alone must never be enough to fire.
    from eliteprocareers.matching.auto_apply import maybe_auto_apply

    track = _fake_track(auto_apply_enabled=True, undo_window_minutes=None)
    result = maybe_auto_apply(
        db=MagicMock(), user_id=uuid4(), track=track, job=_fake_job(),
        match_score=0.99, full_profile=_fake_profile(),
    )
    assert result is False
    mock_app_repo_cls.assert_not_called()


@patch("eliteprocareers.matching.auto_apply.generate_cover_letter")
@patch("eliteprocareers.matching.auto_apply.generate_tailored_cv")
@patch("eliteprocareers.matching.auto_apply.CoverLetterStyleSampleRepository")
@patch("eliteprocareers.matching.auto_apply.DocumentRepository")
@patch("eliteprocareers.matching.auto_apply.ApplicationRepository")
def test_auto_apply_below_threshold_does_nothing(
    mock_app_repo_cls, mock_doc_repo_cls, mock_sample_repo_cls, mock_gen_cv, mock_gen_cl
):
    from eliteprocareers.matching.auto_apply import maybe_auto_apply

    track = _fake_track(auto_apply_min_score=0.85)
    result = maybe_auto_apply(
        db=MagicMock(), user_id=uuid4(), track=track, job=_fake_job(),
        match_score=0.84, full_profile=_fake_profile(),
    )
    assert result is False
    mock_app_repo_cls.assert_not_called()


@patch("eliteprocareers.matching.auto_apply.generate_cover_letter")
@patch("eliteprocareers.matching.auto_apply.generate_tailored_cv")
@patch("eliteprocareers.matching.auto_apply.CoverLetterStyleSampleRepository")
@patch("eliteprocareers.matching.auto_apply.DocumentRepository")
@patch("eliteprocareers.matching.auto_apply.ApplicationRepository")
def test_auto_apply_existing_application_does_nothing(
    mock_app_repo_cls, mock_doc_repo_cls, mock_sample_repo_cls, mock_gen_cv, mock_gen_cl
):
    # Idempotency: a match re-scored on a later matching run for a job
    # that already has an application (manual or auto) must not create
    # a second one.
    from eliteprocareers.matching.auto_apply import maybe_auto_apply

    mock_app_repo = mock_app_repo_cls.return_value
    mock_app_repo.get_application_for_job_and_track.return_value = MagicMock(spec=Application)

    track = _fake_track()
    result = maybe_auto_apply(
        db=MagicMock(), user_id=uuid4(), track=track, job=_fake_job(),
        match_score=0.99, full_profile=_fake_profile(),
    )
    assert result is False
    mock_app_repo.create_queued_application.assert_not_called()


@patch("eliteprocareers.matching.auto_apply.generate_cover_letter")
@patch("eliteprocareers.matching.auto_apply.generate_tailored_cv")
@patch("eliteprocareers.matching.auto_apply.CoverLetterStyleSampleRepository")
@patch("eliteprocareers.matching.auto_apply.DocumentRepository")
@patch("eliteprocareers.matching.auto_apply.ApplicationRepository")
def test_auto_apply_success_creates_queued_application_and_docs(
    mock_app_repo_cls, mock_doc_repo_cls, mock_sample_repo_cls, mock_gen_cv, mock_gen_cl
):
    from eliteprocareers.matching.auto_apply import maybe_auto_apply

    mock_app_repo = mock_app_repo_cls.return_value
    mock_app_repo.get_application_for_job_and_track.return_value = None
    created_app = MagicMock(spec=Application)
    created_app.id = uuid4()
    mock_app_repo.create_queued_application.return_value = created_app

    mock_sample_repo_cls.return_value.get_sample.return_value = None
    mock_gen_cv.return_value = MagicMock(id=uuid4())
    mock_gen_cl.return_value = MagicMock(id=uuid4())

    track = _fake_track()
    job = _fake_job()
    result = maybe_auto_apply(
        db=MagicMock(), user_id=uuid4(), track=track, job=job,
        match_score=0.90, full_profile=_fake_profile(),
    )

    assert result is True
    mock_app_repo.create_queued_application.assert_called_once()
    call_kwargs = mock_app_repo.create_queued_application.call_args.kwargs
    assert call_kwargs["job_id"] == job.id
    assert call_kwargs["cv_track_id"] == track.id
    assert call_kwargs["undo_window_minutes"] == 15
    mock_gen_cv.assert_called_once()
    mock_gen_cl.assert_called_once()


@patch("eliteprocareers.matching.auto_apply.generate_cover_letter")
@patch("eliteprocareers.matching.auto_apply.generate_tailored_cv")
@patch("eliteprocareers.matching.auto_apply.CoverLetterStyleSampleRepository")
@patch("eliteprocareers.matching.auto_apply.DocumentRepository")
@patch("eliteprocareers.matching.auto_apply.ApplicationRepository")
def test_auto_apply_doc_generation_failure_still_creates_application(
    mock_app_repo_cls, mock_doc_repo_cls, mock_sample_repo_cls, mock_gen_cv, mock_gen_cl
):
    # Best-effort doc generation: a Groq hiccup must not prevent the
    # application itself from being created and queued -- the candidate
    # can always generate documents manually afterward.
    from eliteprocareers.matching.auto_apply import maybe_auto_apply

    mock_app_repo = mock_app_repo_cls.return_value
    mock_app_repo.get_application_for_job_and_track.return_value = None
    created_app = MagicMock(spec=Application)
    created_app.id = uuid4()
    mock_app_repo.create_queued_application.return_value = created_app

    mock_sample_repo_cls.return_value.get_sample.return_value = None
    mock_gen_cv.side_effect = Exception("Groq transient error")
    mock_gen_cl.side_effect = Exception("Groq transient error")

    result = maybe_auto_apply(
        db=MagicMock(), user_id=uuid4(), track=_fake_track(), job=_fake_job(),
        match_score=0.90, full_profile=_fake_profile(),
    )
    assert result is True  # application was still created and queued
    mock_app_repo.create_queued_application.assert_called_once()
