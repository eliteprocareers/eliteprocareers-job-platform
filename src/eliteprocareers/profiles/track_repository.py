"""Repository for CV track config: track name, target roles, scoring weights.

Follows the same pattern as ProfileRepository — raw PostgREST dicts are
translated to/from CVTrack here and nowhere else.
"""
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.models import CVTrack


class TrackRepository:
    TABLE = "cv_tracks"

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def create_track(
        self,
        user_id: UUID,
        track_name: str,
        target_roles: list[str] | None = None,
        scoring_weights: dict[str, float] | None = None,
    ) -> CVTrack:
        payload = {
            "user_id": str(user_id),
            "track_name": track_name,
            "target_roles": target_roles or [],
            "scoring_weights": scoring_weights or {},
        }
        rows = self.db.insert(self.TABLE, payload)
        return CVTrack.model_validate(rows[0])

    def list_tracks(self, user_id: UUID) -> list[CVTrack]:
        rows = self.db.select(
            self.TABLE, params={"select": "*", "user_id": f"eq.{user_id}"}
        )
        return [CVTrack.model_validate(r) for r in rows]

    def get_track(self, track_id: UUID) -> CVTrack | None:
        rows = self.db.select(
            self.TABLE, params={"select": "*", "id": f"eq.{track_id}"}
        )
        if not rows:
            return None
        return CVTrack.model_validate(rows[0])

    def update_scoring_weights(
        self, track_id: UUID, scoring_weights: dict[str, float]
    ) -> CVTrack:
        rows = self.db.update(
            self.TABLE,
            data={"scoring_weights": scoring_weights},
            params={"id": f"eq.{track_id}"},
        )
        return CVTrack.model_validate(rows[0])
