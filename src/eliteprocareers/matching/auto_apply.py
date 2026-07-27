"""
Auto-apply trigger (migration 0009, founder decision 2026-07-26).

Called from matching_service.run_matching_for_track right after a job's
match_score is computed and upserted. If the track has auto-apply
enabled and the score clears its threshold, this creates a 'queued'
application and best-effort auto-tailors a CV + cover letter for it --
nothing here submits anything to an employer or ATS. See
ApplicationRepository's module docstring and migration 0009's comment
for the full reasoning (draft-and-queue is deliberate; real per-site
form auto-fill is separate future work, not attempted here).

Idempotent by construction: only fires when no application already
exists for this (user, track, job) triple, so re-running matching for
a track (e.g. after a profile update) never creates duplicate queued
applications for jobs already handled.
"""
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient, SupabaseError
from eliteprocareers.jobs.models import Job
from eliteprocareers.profiles.application_repository import ApplicationRepository
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import CVTrack, FullProfile
from eliteprocareers.generation.cover_letter import generate_cover_letter
from eliteprocareers.generation.cv_tailoring import generate_tailored_cv
from eliteprocareers.profiles.cover_letter_sample_repository import CoverLetterStyleSampleRepository


def maybe_auto_apply(
    db: SupabaseClient,
    user_id: UUID,
    track: CVTrack,
    job: Job,
    match_score: float,
    full_profile: FullProfile,
    organization_id: UUID | None = None,
) -> bool:
    """Returns True if a queued application was created for this job,
    False if auto-apply didn't fire (disabled, below threshold, manual-
    approval-only track, or an application already exists).

    Best-effort on doc generation: if CV/cover-letter generation fails
    (e.g. a transient Groq error), the application still gets created
    and queued -- a candidate can always generate documents manually
    from the existing per-job generation endpoints afterward. This
    function itself never raises for a generation failure; it only
    raises if the application row itself can't be created (a real
    problem the caller -- the matching run -- should surface).
    """
    if not track.auto_apply_enabled:
        return False
    if track.undo_window_minutes is None:
        # Manual-approval-only track: auto_apply_enabled has no effect
        # without an explicit approval step, which doesn't exist yet.
        # Never auto-queue for a track configured this way.
        return False
    if match_score < track.auto_apply_min_score:
        return False

    app_repo = ApplicationRepository(db)
    existing = app_repo.get_application_for_job_and_track(job.id, track.id)
    if existing is not None:
        return False

    try:
        application = app_repo.create_queued_application(
            user_id=user_id,
            job_id=job.id,
            cv_track_id=track.id,
            undo_window_minutes=track.undo_window_minutes,
            organization_id=organization_id,
        )
    except SupabaseError as e:
        # uq_applications_track_job (migration 0010) rejected this insert
        # -- another concurrent matching run (or a manual apply) won the
        # race and already created an application for this exact
        # (track, job) pair between our check above and this insert.
        # Not a real failure: back off quietly instead of crashing this
        # job's iteration of the matching run.
        if "409" in str(e) and "23505" in str(e):
            return False
        raise

    doc_repo = DocumentRepository(db)
    try:
        cv_doc = generate_tailored_cv(
            profile=full_profile,
            track=track,
            job_description=job.description or "",
            doc_repo=doc_repo,
            job_id=job.id,
            organization_id=organization_id,
        )
        if cv_doc.id is not None:
            doc_repo.set_application_id(cv_doc.id, application.id)
    except Exception:
        # Best-effort -- application stays queued either way; the
        # candidate (or a later manual trigger) can generate a CV for
        # it afterward. Not re-raised: a doc-gen hiccup shouldn't ever
        # take down the whole matching run for every other job.
        pass

    try:
        style_sample = CoverLetterStyleSampleRepository(db).get_sample(user_id)
        cover_letter_doc = generate_cover_letter(
            profile=full_profile,
            track=track,
            job_description=job.description or "",
            doc_repo=doc_repo,
            job_id=job.id,
            style_sample_text=style_sample.sample_text if style_sample else None,
            organization_id=organization_id,
        )
        if cover_letter_doc.id is not None:
            doc_repo.set_application_id(cover_letter_doc.id, application.id)
    except Exception:
        pass

    return True
