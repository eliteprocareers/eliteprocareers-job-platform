"""
CV tailoring — builds a prompt from a candidate's real profile + a CV
track + a job description, sends it to the LLM, parses the result into
a CVContent object, and saves it as a new generated_documents version.
"""

import json

from eliteprocareers.generation.llm_client import generate_text, GROQ_MODEL
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import (
    CVContent,
    CVTrack,
    DocType,
    FullProfile,
    GeneratedDocument,
)


class CVGenerationError(Exception):
    """Raised when the LLM response can't be parsed into a valid CVContent."""


def build_cv_prompt(profile: FullProfile, track: CVTrack, job_description: str) -> str:
    skills_text = ", ".join(s.skill_name for s in profile.skills if s.skill_name)

    work_lines = []
    for w in profile.work_experience:
        start = w.start_date or "unknown start date"
        end = "Present" if w.is_current else (w.end_date or "unknown end date")
        work_lines.append(
            f"- {w.title} at {w.company} ({start} to {end}): {w.description or ''}"
        )
    work_text = "\n".join(work_lines)

    education_text = "\n".join(
        f"- {e.degree or ''} in {e.field_of_study or ''}, {e.institution}"
        for e in profile.education
    )
    certs_text = "\n".join(f"- {c.name} ({c.issuer or ''})" for c in profile.certifications)

    return f"""You are tailoring a CV for a specific job application.

TARGET TRACK: {track.track_name}
TARGET ROLES: {", ".join(track.target_roles)}

CANDIDATE SUMMARY (current): {profile.profile.summary or "N/A"}
CANDIDATE SKILLS: {skills_text}
CANDIDATE WORK EXPERIENCE:
{work_text}
CANDIDATE EDUCATION:
{education_text}
CANDIDATE CERTIFICATIONS:
{certs_text}

JOB DESCRIPTION TO TAILOR FOR:
{job_description}

Rewrite the candidate's CV content to best match this job description, using
ONLY real information from the candidate's profile above — do not invent
experience, skills, or credentials that aren't listed.

Respond with ONLY valid JSON (no markdown, no code fences, no commentary)
matching exactly this shape:

{{
  "summary": "2-3 sentence professional summary tailored to this job",
  "skills": ["skill1", "skill2", ...],
  "work_experience": [
    {{"title": "...", "company": "...", "dates": "...", "bullets": ["...", "..."]}}
  ],
  "education": ["degree, institution", ...],
  "certifications": ["cert name, issuer", ...]
}}"""


def _strip_markdown_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_cv_response(raw: str) -> CVContent:
    """Parse the LLM's raw text response into a CVContent object.

    Tolerates markdown code fences, since LLMs wrap JSON in ```json blocks
    even when explicitly told not to.
    """
    cleaned = _strip_markdown_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise CVGenerationError(
            f"LLM response was not valid JSON: {e}\nRaw response:\n{raw}"
        ) from e

    try:
        return CVContent.model_validate(data)
    except Exception as e:
        raise CVGenerationError(
            f"LLM response JSON didn't match CVContent shape: {e}\nParsed data:\n{data}"
        ) from e


def generate_tailored_cv(
    profile: FullProfile,
    track: CVTrack,
    job_description: str,
    doc_repo: DocumentRepository,
    job_id=None,
) -> GeneratedDocument:
    """Full pipeline: build prompt -> call LLM -> parse -> save as a new
    generated_documents version. Returns the saved GeneratedDocument.
    """
    prompt = build_cv_prompt(profile, track, job_description)
    raw_response = generate_text(prompt, temperature=0.5)
    cv_content = parse_cv_response(raw_response)

    return doc_repo.create_document(
        user_id=track.user_id,
        cv_track_id=track.id,
        doc_type=DocType.cv,
        content=cv_content.to_json(),
        job_id=job_id,
        ai_model_used=GROQ_MODEL,
    )
