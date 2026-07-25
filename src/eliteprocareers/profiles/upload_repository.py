"""
CVUploadRepository -- tracks status of background CV-parse jobs
(cv_uploads table), for real status-polling via
GET /profile/cv-upload-status/{upload_id}. Direct structural mirror of
MatchingRunRepository (matching/repository.py) -- same trigger-then-poll
shape the frontend already knows from Stage 2.

RLS note: cv_uploads has a user-scoped RLS policy (user_id = auth.uid()),
same as matching_runs. This repository must be constructed with a
normal user-scoped SupabaseClient (access_token path), not
use_service_role=True. See migrations/0005_add_cv_uploads.sql.
"""
from datetime import datetime, timezone
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.models import CVUpload


class CVUploadRepository:
    TABLE = "cv_uploads"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def create_upload(
        self, user_id: UUID, filename: str, file_size_bytes: int
    ) -> CVUpload:
        """Called synchronously, before the background parse task starts,
        so the client always gets a real upload_id to poll -- same
        reason MatchingRunRepository.create_run() is called synchronously
        in tracks.py's trigger_matching().
        """
        payload = {
            "user_id": str(user_id),
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "status": "processing",
        }
        rows = self.db.insert(self.TABLE, payload)
        return CVUpload.model_validate(rows[0])

    def mark_completed(
        self, upload_id: UUID, raw_text: str, fields_extracted: int
    ) -> None:
        self.db.update(
            self.TABLE,
            {
                "status": "completed",
                "raw_text": raw_text,
                "fields_extracted": fields_extracted,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            params={"id": f"eq.{upload_id}"},
        )

    def mark_failed(self, upload_id: UUID, error_message: str) -> None:
        """error_message is str(exc), not a full traceback -- same rule
        as MatchingRunRepository.mark_failed(), to avoid leaking internal
        details to a client polling this row.
        """
        self.db.update(
            self.TABLE,
            {
                "status": "failed",
                "error_message": error_message,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            params={"id": f"eq.{upload_id}"},
        )

    def get_upload(self, upload_id: UUID) -> CVUpload | None:
        rows = self.db.select(
            self.TABLE, params={"select": "*", "id": f"eq.{upload_id}"}
        )
        if not rows:
            return None
        return CVUpload.model_validate(rows[0])
