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
        preferred_locations: list[str] | None = None,
        preferred_countries: list[str] | None = None,
        employment_types: list[str] | None = None,
        seniority_levels: list[str] | None = None,
        industries: list[str] | None = None,
        work_mode: list[str] | None = None,
        willing_to_relocate: bool = False,
        visa_sponsorship_required: bool | None = None,
        work_authorization_status: str | None = None,
        salary_expectation_min: float | None = None,
        salary_expectation_max: float | None = None,
        salary_currency: str | None = None,
        auto_apply_enabled: bool = False,
        auto_apply_min_score: float = 0.85,
        undo_window_minutes: int | None = 15,
    ) -> CVTrack:
        payload = {
            "user_id": str(user_id),
            "track_name": track_name,
            "target_roles": target_roles or [],
            "scoring_weights": scoring_weights or {},
            "preferred_locations": preferred_locations or [],
            "preferred_countries": preferred_countries or [],
            "employment_types": employment_types or [],
            "seniority_levels": seniority_levels or [],
            "industries": industries or [],
            "work_mode": work_mode or [],
            "willing_to_relocate": willing_to_relocate,
            "visa_sponsorship_required": visa_sponsorship_required,
            "work_authorization_status": work_authorization_status,
            "salary_expectation_min": salary_expectation_min,
            "salary_expectation_max": salary_expectation_max,
            "salary_currency": salary_currency,
            "auto_apply_enabled": auto_apply_enabled,
            "auto_apply_min_score": auto_apply_min_score,
            "undo_window_minutes": undo_window_minutes,
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

    def update_track(self, track_id: UUID, **fields) -> CVTrack:
        """Partial update of arbitrary track fields (track_name, target_roles,
        preferences, salary expectations, etc.) -- unlike
        update_scoring_weights, this accepts any subset of CVTrack's mutable
        fields. Caller (the API router) is responsible for excluding unset
        fields via payload.model_dump(exclude_unset=True) so an omitted
        field isn't overwritten with a default.
        """
        if not fields:
            raise ValueError("update_track called with no fields to update.")
        rows = self.db.update(
            self.TABLE, data=fields, params={"id": f"eq.{track_id}"}
        )
        return CVTrack.model_validate(rows[0])
