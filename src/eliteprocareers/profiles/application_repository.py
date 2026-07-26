"""Repository for applications: Stage 5 (submission) status tracking.

Draft-and-queue model -- this table records what stage an application is
in (draft/submitted/interviewing/rejected/offer/withdrawn); nothing in
this repository or the API layer above it ever submits anything to an
employer or ATS on the user's behalf. That's a deliberate, separate
decision (see the Stage 5 handover) -- not a gap to "finish" later without
revisiting the ToS/infrastructure tradeoffs it was made against.
"""
from datetime import datetime, timezone
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
    ) -> Application:
        payload = {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "cv_track_id": str(cv_track_id),
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
