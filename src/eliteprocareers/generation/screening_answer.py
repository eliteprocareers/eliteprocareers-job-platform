"""
Screening answer generation — answers a single application screening
question (e.g. "Why do you want to work here?") using the candidate's
real profile + a CV track + the job description for context.

Same pattern as cover_letter.py: plain text in, plain text out, no
JSON parsing. Saved as its own generated_documents version.
"""

from eliteprocareers.generation.llm_client import generate_text, GROQ_MODEL
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import CVTrack, DocType, FullProfile, GeneratedDocument


def build_screening_answer_prompt(
    profile: FullProfile,
    track: CVTrack,
    job_description: str,
    question: str,
    word_limit: int | None = None,
) -> str:
    skills_text = ", ".join(s.skill_name for s in profile.skills if s.skill_name)

    work_lines = []
    for w in profile.work_experience:
        end = "Present" if w.is_current else (w.end_date or "")
        work_lines.append(
            f"- {w.title} at {w.company} ({w.start_date} to {end}): {w.description or ''}"
        )
    work_text = "\n".join(work_lines)

    limit_instruction = (
        f"Keep the answer under {word_limit} words."
        if word_limit
        else "Keep the answer concise — 3-5 sentences, no more than about 150 words."
    )

    return f"""You are answering a job application screening question on
behalf of a candidate.

TARGET TRACK: {track.track_name}
TARGET ROLES: {", ".join(track.target_roles)}

CANDIDATE SUMMARY: {profile.profile.summary or "N/A"}
CANDIDATE SKILLS: {skills_text}
CANDIDATE WORK EXPERIENCE:
{work_text}

JOB DESCRIPTION (for context):
{job_description}

SCREENING QUESTION TO ANSWER:
{question}

Write a first-person answer to this screening question, using ONLY real
information from the candidate's profile above — do not invent experience,
skills, credentials, or achievements that aren't listed. If the profile
doesn't fully support a strong answer, answer honestly based on what's
actually there rather than fabricating a better fit. {limit_instruction}

Respond with ONLY the answer text — no commentary, no markdown formatting,
no restating of the question, no code fences."""


def generate_screening_answer(
    profile: FullProfile,
    track: CVTrack,
    job_description: str,
    question: str,
    doc_repo: DocumentRepository,
    word_limit: int | None = None,
    job_id=None,
) -> GeneratedDocument:
    """Full pipeline: build prompt -> call LLM -> save as a new
    generated_documents version. Returns the saved GeneratedDocument.
    """
    prompt = build_screening_answer_prompt(profile, track, job_description, question, word_limit)
    raw_response = generate_text(prompt, temperature=0.7)
    content = raw_response.strip()

    return doc_repo.create_document(
        user_id=track.user_id,
        cv_track_id=track.id,
        doc_type=DocType.screening_answer,
        content=content,
        job_id=job_id,
        ai_model_used=GROQ_MODEL,
    )
