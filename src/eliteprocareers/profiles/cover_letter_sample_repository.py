"""
CoverLetterStyleSampleRepository -- one writing sample per user, used
only to steer tone/style of future AI-generated cover letters (see
CoverLetterStyleSample's docstring in models.py). Structural mirror of
CVUploadRepository, but simpler: no background job, no status polling
-- extraction is fast and synchronous (reuses document_extraction.py,
no LLM call involved), so there's nothing to poll.

RLS note: cover_letter_style_samples has a user-scoped RLS policy
(user_id = auth.uid()), same as cv_uploads. Construct this repository
with a normal user-scoped SupabaseClient, not use_service_role=True.
See migrations/0008_add_cover_letter_style_samples.sql.
"""
from datetime import datetime, timezone
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.models import CoverLetterStyleSample


class CoverLetterStyleSampleRepository:
    TABLE = "cover_letter_style_samples"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def upsert_sample(
        self, user_id: UUID, filename: str, sample_text: str
    ) -> CoverLetterStyleSample:
        """Replaces any existing sample for this user. SupabaseClient has
        no upsert() method (confirmed against db/client.py -- only
        select/insert/update/delete exist), so this does a real
        check-then-insert-or-update rather than assuming one.
        """
        existing = self.get_sample(user_id)
        payload = {
            "filename": filename,
            "sample_text": sample_text,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        if existing is None:
            rows = self.db.insert(self.TABLE, {"user_id": str(user_id), **payload})
        else:
            rows = self.db.update(
                self.TABLE, payload, params={"user_id": f"eq.{user_id}"}
            )
        return CoverLetterStyleSample.model_validate(rows[0])

    def get_sample(self, user_id: UUID) -> CoverLetterStyleSample | None:
        rows = self.db.select(
            self.TABLE, params={"select": "*", "user_id": f"eq.{user_id}"}
        )
        if not rows:
            return None
        return CoverLetterStyleSample.model_validate(rows[0])

    def delete_sample(self, user_id: UUID) -> bool:
        """Returns True if a sample existed and was removed, False if
        there was nothing to delete -- lets the router 404 correctly.
        """
        existing = self.get_sample(user_id)
        if existing is None:
            return False
        self.db.delete(self.TABLE, params={"user_id": f"eq.{user_id}"})
        return True
