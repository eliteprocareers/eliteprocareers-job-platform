"""
Cover letter generation — builds a prompt from a candidate's real profile +
a CV track + a job description, sends it to the LLM, and saves the plain-text
result as a new generated_documents version.

Simpler than CV tailoring: no JSON schema, no parsing step — the LLM's raw
text response (after trimming) is the final saved content.
"""

from eliteprocareers.generation.llm_client import generate_text, GROQ_MODEL
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import CVTrack, DocType, FullProfile, GeneratedDocument


def build_cover_letter_prompt(profile: FullProfile, track: CVTrack, job_description: str) -> str:
    skills_text = ", ".join(s.skill_name for s in profile.skills if s.skill_name)

    work_lines = []
    for w in profile.work_experience:
        end = "Present" if w.is_current else (w.end_date or "")
        work_lines.append(
            f"- {w.title} at {w.company} ({w.start_date} to {end}): {w.description or ''}"
        )
    work_text = "\n".join(work_lines)

    return f"""You are writing a cover letter for a specific job application.

TARGET TRACK: {track.track_name}
TARGET ROLES: {", ".join(track.target_roles)}

CANDIDATE SUMMARY: {profile.profile.summary or "N/A"}
CANDIDATE SKILLS: {skills_text}
CANDIDATE WORK EXPERIENCE:
{work_text}

JOB DESCRIPTION TO WRITE FOR:
{job_description}

Write a professional cover letter tailored to this job description, using
ONLY real information from the candidate's profile above — do not invent
experience, skills, or credentials that aren't listed. Keep it to 3-4
paragraphs, no more than about 350 words. Do not include a date, address
block, or placeholder brackets like "[Hiring Manager's Name]" — start
directly with the salutation "Dear Hiring Manager," and end with a
professional sign-off ("Sincerely,").

Respond with ONLY the cover letter text — no commentary, no markdown
formatting, no code fences."""


def generate_cover_letter(
    profile: FullProfile,
    track: CVTrack,
    job_description: str,
    doc_repo: DocumentRepository,
) -> GeneratedDocument:
    """Full pipeline: build prompt -> call LLM -> save as a new
    generated_documents version. Returns the saved GeneratedDocument.
    """
    prompt = build_cover_letter_prompt(profile, track, job_description)
    raw_response = generate_text(prompt, temperature=0.7)
    content = raw_response.strip()

    return doc_repo.create_document(
        user_id=track.user_id,
        cv_track_id=track.id,
        doc_type=DocType.cover_letter,
        content=content,
        ai_model_used=GROQ_MODEL,
    )
