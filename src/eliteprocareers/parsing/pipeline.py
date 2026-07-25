"""
Full CV-upload pipeline: raw file bytes -> extracted text -> LLM
extraction -> persisted candidate_profiles + related rows -> cv_uploads
status update. Wired to POST /profile/cv-upload via BackgroundTasks,
same shape as matching_service.run_matching_for_track_tracked wired to
POST /tracks/{id}/match.
"""
from uuid import UUID

from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.parsing.cv_parser import extract_cv_profile
from eliteprocareers.parsing.document_extraction import (
    ExtractionError,
    extract_text_from_file,
)
from eliteprocareers.profiles.models import ParsedCVProfile
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.upload_repository import CVUploadRepository


def save_parsed_profile(
    user_id: UUID, parsed: ParsedCVProfile, profile_repo: ProfileRepository
) -> int:
    """Persists a ParsedCVProfile into candidate_profiles + related
    tables. Returns a count of fields/rows written, for cv_uploads.
    fields_extracted (a rough signal for the client, not an exact
    schema-field count).

    Base-profile fields: only the ones the CV actually had (non-None in
    `parsed`) are written. On first upload this creates the profile; on
    a re-upload it updates only those same non-None fields, leaving
    anything the user has since edited by hand untouched if this CV
    didn't mention it.

    List fields (skills, work_experience, education, certifications,
    languages, projects): appended as new rows every time, with no
    dedup/replace against existing rows. A second upload for the same
    user will duplicate anything already saved. This is a known,
    deliberate MVP limitation -- see handover -- rather than an
    oversight; proper dedup/versioning needs a UX decision (replace
    entirely? merge? let the user pick per-row?) that hasn't been made.
    """
    base_fields = {
        k: v
        for k, v in {
            "full_name": parsed.full_name,
            "headline": parsed.headline,
            "summary": parsed.summary,
            "location": parsed.location,
            "email": parsed.email,
            "phone": parsed.phone,
            "linkedin_url": parsed.linkedin_url,
            "portfolio_url": parsed.portfolio_url,
        }.items()
        if v is not None
    }

    existing = profile_repo.get_profile_by_user(user_id)
    if existing is None:
        profile = profile_repo.create_profile(user_id=user_id, **base_fields)
    elif base_fields:
        profile = profile_repo.update_profile(existing.id, **base_fields)
    else:
        profile = existing

    fields_written = len(base_fields)

    for skill_name in parsed.skills:
        profile_repo.add_skill(profile.id, skill_name)
    fields_written += len(parsed.skills)

    for work in parsed.work_experience:
        profile_repo.add_work_experience(
            profile.id,
            company=work.company,
            title=work.title,
            location=work.location,
            is_current=work.is_current,
            description=_with_date_text(work.description, work.start_date_text, work.end_date_text),
        )
    fields_written += len(parsed.work_experience)

    for edu in parsed.education:
        profile_repo.add_education(
            profile.id,
            institution=edu.institution,
            degree=edu.degree,
            field_of_study=edu.field_of_study,
            description=_date_range_text(edu.start_date_text, edu.end_date_text),
        )
    fields_written += len(parsed.education)

    for cert in parsed.certifications:
        profile_repo.add_certification(profile.id, name=cert.name, issuer=cert.issuer)
    fields_written += len(parsed.certifications)

    for lang in parsed.languages:
        profile_repo.add_language(
            profile.id,
            language=lang.language,
            proficiency=lang.proficiency.value if lang.proficiency else None,
        )
    fields_written += len(parsed.languages)

    for project in parsed.projects:
        profile_repo.add_project(
            profile.id, name=project.name, description=project.description, url=project.url
        )
    fields_written += len(parsed.projects)

    return fields_written


def _date_range_text(start_text: str | None, end_text: str | None) -> str | None:
    """education.start_date/end_date are real `date` columns (unlike
    work_experience's is_current + description split above) that this
    pipeline deliberately doesn't attempt to populate -- parsing free-text
    dates like "2019" or "Sep 2018" into a real date without inventing a
    day/month the CV never specified risks writing a wrong-but-plausible
    value into a typed column. Folding the raw text into `description`
    instead keeps it visible without fabricating precision. Normalizing
    this properly is a known follow-up (same note as ParsedWorkExperience's
    docstring), not attempted here.
    """
    if not start_text and not end_text:
        return None
    return f"{start_text or 'unknown start'} - {end_text or 'unknown end'}"


def _with_date_text(
    description: str | None, start_text: str | None, end_text: str | None
) -> str | None:
    date_range = _date_range_text(start_text, end_text)
    if not date_range:
        return description
    if not description:
        return f"({date_range})"
    return f"({date_range}) {description}"


def parse_cv_upload_tracked(
    user_id: UUID,
    upload_id: UUID,
    filename: str,
    content: bytes,
    db: SupabaseClient,
) -> None:
    """The background-task entrypoint for POST /profile/cv-upload.
    Extracts text, runs LLM extraction, persists into the profile
    tables, and marks the cv_uploads row completed/failed -- mirrors
    matching_service.run_matching_for_track_tracked's try/except/mark_*
    shape exactly. db must be user-scoped (not service_role), same RLS
    rule as everywhere else in this API layer.
    """
    upload_repo = CVUploadRepository(db)
    profile_repo = ProfileRepository(db)

    try:
        raw_text = extract_text_from_file(filename, content)
        parsed = extract_cv_profile(raw_text)
        fields_extracted = save_parsed_profile(user_id, parsed, profile_repo)
        upload_repo.mark_completed(upload_id, raw_text=raw_text, fields_extracted=fields_extracted)
    except ExtractionError as exc:
        # Expected failure mode (unreadable/scanned file) -- still
        # re-raised after marking failed so it shows up in server logs,
        # same as the unexpected-exception branch below.
        upload_repo.mark_failed(upload_id, str(exc))
        raise
    except Exception as exc:
        upload_repo.mark_failed(upload_id, str(exc))
        raise
