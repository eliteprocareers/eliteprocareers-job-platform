"""Repository for generated_documents: versioned CV/cover letter/screening
answer content. Rows are never overwritten — a new version is inserted
each time content is regenerated, so history is preserved.

Versioning is scoped to (cv_track_id, job_id, doc_type): regenerating a
CV for the same job increments its version; generating for a different
job under the same track starts its own version sequence.
"""
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.models import DocType, GeneratedDocument


class DocumentRepository:
    TABLE = "generated_documents"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def create_document(
        self,
        user_id: UUID,
        cv_track_id: UUID,
        doc_type: DocType,
        content: str,
        job_id: UUID | None = None,
        ai_model_used: str | None = None,
        application_id: UUID | None = None,
    ) -> GeneratedDocument:
        """Insert a new document version. version is computed automatically
        as (highest existing version for this track+job+doc_type) + 1.
        """
        existing = self.list_versions(cv_track_id, doc_type, job_id=job_id)
        next_version = (max((d.version for d in existing), default=0)) + 1

        payload = {
            "user_id": str(user_id),
            "cv_track_id": str(cv_track_id),
            "job_id": str(job_id) if job_id else None,
            "application_id": str(application_id) if application_id else None,
            "doc_type": doc_type.value,
            "content": content,
            "version": next_version,
            "ai_model_used": ai_model_used,
        }
        rows = self.db.insert(self.TABLE, payload)
        return GeneratedDocument.model_validate(rows[0])

    def list_versions(
        self, cv_track_id: UUID, doc_type: DocType, job_id: UUID | None = None
    ) -> list[GeneratedDocument]:
        params = {
            "select": "*",
            "cv_track_id": f"eq.{cv_track_id}",
            "doc_type": f"eq.{doc_type.value}",
            "order": "version.asc",
        }
        params["job_id"] = f"eq.{job_id}" if job_id else "is.null"
        rows = self.db.select(self.TABLE, params=params)
        return [GeneratedDocument.model_validate(r) for r in rows]

    def get_latest_document(
        self, cv_track_id: UUID, doc_type: DocType, job_id: UUID | None = None
    ) -> GeneratedDocument | None:
        versions = self.list_versions(cv_track_id, doc_type, job_id=job_id)
        if not versions:
            return None
        return versions[-1]

    def set_application_id(
        self, document_id: UUID, application_id: UUID
    ) -> GeneratedDocument:
        """Link an already-generated document to an application, once one
        exists for its (track, job) pair. Called from applications.py right
        after an application is created -- never on the generate-* path
        itself, since a document can be generated before any application
        exists.
        """
        rows = self.db.update(
            self.TABLE,
            data={"application_id": str(application_id)},
            params={"id": f"eq.{document_id}"},
        )
        return GeneratedDocument.model_validate(rows[0])
