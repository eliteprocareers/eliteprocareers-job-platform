"""Repository for applications: Stage 5 (submission) status tracking.

Draft-and-queue model -- this table records what stage an application is
in; nothing in this repository or the API layer above it ever submits
anything to an employer or ATS on the user's behalf. That's a deliberate,
separate decision (see the Stage 5 handover) -- not a gap to "finish"
later without revisiting the ToS/infrastructure tradeoffs it was made
against.

Extended 2026-07-26 (migration 0009) with an autonomous trigger path:
a match scoring >= a track's auto_apply_min_score can create a 'queued'
application automatically (create_queued_application), which advances to
'ready_to_submit' after its undo window (advance_expired_queued) unless
cancelled. This still doesn't submit anything automatically -- the
candidate finishes the real submission by hand at 'ready_to_submit'.
Per-site form auto-fill is future work, not built here; see migration
0009's own comment for why.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.models import Application, ApplicationStatus


class ApplicationRepository:
    TABLE = "applications"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def create_application(
        self,
        user_id: UUID,
        job_id: UUID,
        cv_track_id: UUID,
        notes: str | None = None,
        organization_id: UUID | None = None,
    ) -> Application:
        payload = {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "cv_track_id": str(cv_track_id),
            "organization_id": str(organization_id) if organization_id else None,
            "status": ApplicationStatus.draft.value,
            "notes": notes,
        }
        rows = self.db.insert(self.TABLE, payload)
        return Application.model_validate(rows[0])

    def get_application(self, application_id: UUID) -> Application | None:
        rows = self.db.select(
            self.TABLE, params={"select": "*", "id": f"eq.{application_id}"}
        )
        if not rows:
            return None
        return Application.model_validate(rows[0])

    def list_applications_for_track(self, cv_track_id: UUID) -> list[Application]:
        rows = self.db.select(
            self.TABLE,
            params={
                "select": "*",
                "cv_track_id": f"eq.{cv_track_id}",
                "order": "created_at.desc",
            },
        )
        return [Application.model_validate(r) for r in rows]

    def get_application_for_job_and_track(
        self, job_id: UUID, cv_track_id: UUID
    ) -> Application | None:
        """Used by auto-apply's idempotency check -- at most one
        application should ever exist per (job, track) pair, whether
        created manually or by auto-apply, so re-running matching for a
        track never creates a duplicate queued application for a job
        already handled.
        """
        rows = self.db.select(
            self.TABLE,
            params={
                "select": "*",
                "job_id": f"eq.{job_id}",
                "cv_track_id": f"eq.{cv_track_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return Application.model_validate(rows[0])

    def create_queued_application(
        self,
        user_id: UUID,
        job_id: UUID,
        cv_track_id: UUID,
        undo_window_minutes: int,
        organization_id: UUID | None = None,
    ) -> Application:
        """Auto-apply's entry point -- creates an application already in
        'queued' status (never 'draft'), auto_applied=True, with
        undo_deadline set to now + undo_window_minutes. Distinct from
        create_application (the pre-existing manual draft-and-queue
        path) so the two flows can't be confused by callers.
        """
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(minutes=undo_window_minutes)
        payload = {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "cv_track_id": str(cv_track_id),
            "organization_id": str(organization_id) if organization_id else None,
            "status": ApplicationStatus.queued.value,
            "auto_applied": True,
            "queued_at": now.isoformat(),
            "undo_deadline": deadline.isoformat(),
        }
        rows = self.db.insert(self.TABLE, payload)
        return Application.model_validate(rows[0])

    def cancel_queued_application(self, application_id: UUID) -> Application:
        """Candidate-initiated cancel during the undo window. Only valid
        from 'queued' -- callers (the router) are responsible for
        checking current status and the deadline before calling this,
        same division of responsibility as update_status's applied_at
        rule.
        """
        rows = self.db.update(
            self.TABLE,
            data={"status": ApplicationStatus.cancelled.value},
            params={"id": f"eq.{application_id}"},
        )
        return Application.model_validate(rows[0])

    def advance_expired_queued(self, applications: list[Application]) -> list[Application]:
        """Lazy status transition -- called on every read (list_applications_
        for_track), not via a background job/cron. Any 'queued' application
        whose undo_deadline has passed advances to 'ready_to_submit' here,
        one UPDATE per expired row. Deliberately no server-side action
        beyond the status flip: real per-site auto-fill/submission isn't
        built yet (see migration 0009's comment) -- 'ready_to_submit' is
        the real, current end state, not a placeholder for something that
        already fires automatically.
        """
        now = datetime.now(timezone.utc)
        advanced: list[Application] = []
        for app in applications:
            if (
                app.status == ApplicationStatus.queued
                and app.undo_deadline is not None
                and app.undo_deadline <= now
                and app.id is not None
            ):
                rows = self.db.update(
                    self.TABLE,
                    data={"status": ApplicationStatus.ready_to_submit.value},
                    params={"id": f"eq.{app.id}"},
                )
                advanced.append(Application.model_validate(rows[0]))
            else:
                advanced.append(app)
        return advanced

    def mark_needs_attention(self, application_id: UUID, failure_reason: str) -> Application:
        """Failure-handling plumbing (founder decision 2026-07-26): retry
        transient failures up to 3x with backoff, then move here and
        notify -- never retry if there's duplicate-submission risk.
        Dormant until real submission automation exists (nothing calls
        this yet), but the contract is real: once that lands, it must
        honor this exact status + retry_count bookkeeping, not invent a
        parallel mechanism.
        """
        rows = self.db.update(
            self.TABLE,
            data={
                "status": ApplicationStatus.needs_attention.value,
                "failure_reason": failure_reason,
                "last_attempt_at": datetime.now(timezone.utc).isoformat(),
            },
            params={"id": f"eq.{application_id}"},
        )
        return Application.model_validate(rows[0])

    def increment_retry(self, application_id: UUID) -> Application:
        current = self.get_application(application_id)
        if current is None:
            raise ValueError(f"Application {application_id} not found.")
        rows = self.db.update(
            self.TABLE,
            data={
                "retry_count": current.retry_count + 1,
                "last_attempt_at": datetime.now(timezone.utc).isoformat(),
            },
            params={"id": f"eq.{application_id}"},
        )
        return Application.model_validate(rows[0])

    def update_status(
        self,
        application_id: UUID,
        status: ApplicationStatus,
        notes: str | None = None,
    ) -> Application:
        """Update status, and notes if provided. applied_at is set
        automatically the first time status moves to 'submitted' --
        callers never set it directly, so it can't be backdated or
        forged via the API. Left untouched on every other transition,
        including a later move back through submitted-adjacent statuses.
        """
        data: dict = {"status": status.value}
        if notes is not None:
            data["notes"] = notes
        if status == ApplicationStatus.submitted:
            current = self.get_application(application_id)
            if current is not None and current.applied_at is None:
                data["applied_at"] = datetime.now(timezone.utc).isoformat()

        rows = self.db.update(
            self.TABLE, data=data, params={"id": f"eq.{application_id}"}
        )
        return Application.model_validate(rows[0])
