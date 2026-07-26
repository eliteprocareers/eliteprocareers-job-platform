"""
ProfileRepository — the boundary between raw PostgREST dicts and typed
domain models. Every other module should interact with profile data
through this class, never through SupabaseClient directly for profile
tables.

Usage:
    from eliteprocareers.db.auth import sign_in
    from eliteprocareers.db.client import SupabaseClient
    from eliteprocareers.profiles.repository import ProfileRepository

    session = sign_in(email, password)
    db = SupabaseClient(access_token=session["access_token"])
    repo = ProfileRepository(db)

    profile = repo.create_profile(user_id=..., full_name="James Maina")
    full = repo.get_full_profile(profile.id)
"""

from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.profiles.models import (
    Achievement,
    CandidateProfile,
    CandidateSkill,
    Certification,
    Education,
    FullProfile,
    Language,
    Project,
    Reference,
    Skill,
    WorkExperience,
)


class ProfileRepository:
    def __init__(self, db: SupabaseClient):
        self.db = db

    # --- candidate_profiles ---

    def create_profile(self, user_id: UUID, **fields) -> CandidateProfile:
        payload = {"user_id": str(user_id), **fields}
        rows = self.db.insert("candidate_profiles", payload)
        return CandidateProfile.model_validate(rows[0])

    def get_profile_by_user(self, user_id: UUID) -> CandidateProfile | None:
        rows = self.db.select(
            "candidate_profiles",
            params={"select": "*", "user_id": f"eq.{user_id}"},
        )
        return CandidateProfile.model_validate(rows[0]) if rows else None

    def update_profile(self, profile_id: UUID, **fields) -> CandidateProfile:
        rows = self.db.update(
            "candidate_profiles", fields, params={"id": f"eq.{profile_id}"}
        )
        return CandidateProfile.model_validate(rows[0])

    # --- skills (shared catalog) + candidate_skills (join) ---

    def get_or_create_skill(self, name: str) -> Skill:
        rows = self.db.select("skills", params={"select": "*", "name": f"eq.{name}"})
        if rows:
            return Skill.model_validate(rows[0])
        rows = self.db.insert("skills", {"name": name})
        return Skill.model_validate(rows[0])

    def add_skill(
        self,
        profile_id: UUID,
        skill_name: str,
        proficiency_level: str | None = None,
        years_experience: float | None = None,
    ) -> CandidateSkill:
        skill = self.get_or_create_skill(skill_name)
        payload = {
            "profile_id": str(profile_id),
            "skill_id": str(skill.id),
            "proficiency_level": proficiency_level,
            "years_experience": years_experience,
        }
        existing = self.db.select(
            "candidate_skills",
            params={
                "select": "*",
                "profile_id": f"eq.{profile_id}",
                "skill_id": f"eq.{skill.id}",
            },
        )
        if existing:
            # Skill already linked to this profile (e.g. re-uploading a CV
            # that lists the same skill again) -- update the existing row
            # instead of inserting a duplicate, which the DB's unique
            # constraint (candidate_skills_profile_id_skill_id_key) rejects.
            rows = self.db.update(
                "candidate_skills",
                {
                    "proficiency_level": proficiency_level,
                    "years_experience": years_experience,
                },
                params={"id": f"eq.{existing[0]['id']}"},
            )
        else:
            rows = self.db.insert("candidate_skills", payload)
        result = CandidateSkill.model_validate(rows[0])
        result.skill_name = skill.name
        return result

    def list_skills(self, profile_id: UUID) -> list[CandidateSkill]:
        # Pull skill name via PostgREST embedded resource in one round trip
        rows = self.db.select(
            "candidate_skills",
            params={
                "select": "*,skills(name)",
                "profile_id": f"eq.{profile_id}",
            },
        )
        results = []
        for row in rows:
            skill_name = row.pop("skills", {}).get("name") if row.get("skills") else None
            item = CandidateSkill.model_validate(row)
            item.skill_name = skill_name
            results.append(item)
        return results

    # --- work_experience ---

    def add_work_experience(self, profile_id: UUID, **fields) -> WorkExperience:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("work_experience", payload)
        return WorkExperience.model_validate(rows[0])

    def list_work_experience(self, profile_id: UUID) -> list[WorkExperience]:
        rows = self.db.select(
            "work_experience", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [WorkExperience.model_validate(r) for r in rows]

    # --- education ---

    def add_education(self, profile_id: UUID, **fields) -> Education:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("education", payload)
        return Education.model_validate(rows[0])

    def list_education(self, profile_id: UUID) -> list[Education]:
        rows = self.db.select(
            "education", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [Education.model_validate(r) for r in rows]

    # --- certifications ---

    def add_certification(self, profile_id: UUID, **fields) -> Certification:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("certifications", payload)
        return Certification.model_validate(rows[0])

    def list_certifications(self, profile_id: UUID) -> list[Certification]:
        rows = self.db.select(
            "certifications", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [Certification.model_validate(r) for r in rows]

    # --- languages ---

    def add_language(self, profile_id: UUID, **fields) -> Language:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("languages", payload)
        return Language.model_validate(rows[0])

    def list_languages(self, profile_id: UUID) -> list[Language]:
        rows = self.db.select(
            "languages", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [Language.model_validate(r) for r in rows]

    # --- projects ---

    def add_project(self, profile_id: UUID, **fields) -> Project:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("projects", payload)
        return Project.model_validate(rows[0])

    def list_projects(self, profile_id: UUID) -> list[Project]:
        rows = self.db.select(
            "projects", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [Project.model_validate(r) for r in rows]

    # --- achievements ---

    def add_achievement(self, profile_id: UUID, **fields) -> Achievement:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("achievements", payload)
        return Achievement.model_validate(rows[0])

    def list_achievements(self, profile_id: UUID) -> list[Achievement]:
        rows = self.db.select(
            "achievements", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [Achievement.model_validate(r) for r in rows]

    # --- references ---

    def add_reference(self, profile_id: UUID, **fields) -> Reference:
        payload = {"profile_id": str(profile_id), **fields}
        rows = self.db.insert("references", payload)
        return Reference.model_validate(rows[0])

    def list_references(self, profile_id: UUID) -> list[Reference]:
        rows = self.db.select(
            "references", params={"select": "*", "profile_id": f"eq.{profile_id}"}
        )
        return [Reference.model_validate(r) for r in rows]

    # --- composite ---

    def get_full_profile(self, user_id: UUID) -> FullProfile | None:
        profile = self.get_profile_by_user(user_id)
        if not profile:
            return None
        return FullProfile(
            profile=profile,
            skills=self.list_skills(profile.id),
            work_experience=self.list_work_experience(profile.id),
            education=self.list_education(profile.id),
            certifications=self.list_certifications(profile.id),
            languages=self.list_languages(profile.id),
            projects=self.list_projects(profile.id),
            achievements=self.list_achievements(profile.id),
            references=self.list_references(profile.id),
        )
