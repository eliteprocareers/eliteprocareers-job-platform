"""
Match rationale generation -- a short, human-readable explanation of why
a specific job was scored as a match for a specific CV track, grounded in
the candidate's real profile.

This is what turns "1,697 correctly-filtered matches exist" into "the
matches are actually useful to read" (v9 handover, recommended next task).
Fills the `ai_rationale` column on user_job_matches, which has existed in
the schema and domain model since matching/models.py was written but has
never been populated (confirmed live 2026-07-20: 0/697 rows have a
rationale).

Same pattern as screening_answer.py: plain text in, plain text out, no
JSON parsing, Groq via generation/llm_client.py. Does NOT write to the
database itself -- callers own the write, same separation scoring/embeddings.py
already uses (it computes, it doesn't persist).
"""

from eliteprocareers.generation.llm_client import GROQ_MODEL_FAST, generate_text
from eliteprocareers.jobs.models import Job
from eliteprocareers.profiles.models import CVTrack, FullProfile
from eliteprocareers.text_utils import clean_html_text

# Cap applied to job.description before it goes in the prompt. Confirmed
# live 2026-07-20: a real posting (Asana "People Partner, APJ") stored
# 17,577 chars of raw HTML-entity-escaped markup as its description --
# ~4,000+ tokens on its own, reliably blowing the fast model's 6,000 TPM
# cap on every retry regardless of pacing. Descriptions this long add
# nothing a 2-3 sentence rationale needs anyway; the opening paragraphs
# carry the substance, everything past this is boilerplate/benefits/EEO text.
_MAX_DESCRIPTION_CHARS = 1200


def _clean_description(raw: str | None) -> str:
    """Strips HTML tags/entities and truncates for prompt use.

    v13: now a thin wrapper around the shared clean_html_text() helper
    (see text_utils.py) so scoring/embeddings.py can reuse the same
    HTML-stripping logic. Behavior/output unchanged from v11.
    """
    return clean_html_text(raw, max_chars=_MAX_DESCRIPTION_CHARS) or "Not provided"


def build_rationale_prompt(
    profile: FullProfile,
    track: CVTrack,
    job: Job,
    match_score: float,
) -> str:
    skills_text = ", ".join(s.skill_name for s in profile.skills if s.skill_name)

    work_lines = []
    for w in profile.work_experience:
        end = "Present" if w.is_current else (w.end_date or "")
        work_lines.append(f"- {w.title} at {w.company} ({w.start_date} to {end})")
    work_text = "\n".join(work_lines)

    return f"""You are explaining, to the candidate themselves, why a specific
job posting was surfaced as a match under one of their CV tracks.

TARGET TRACK: {track.track_name}
TARGET ROLES: {", ".join(track.target_roles)}

CANDIDATE SUMMARY: {profile.profile.summary or "N/A"}
CANDIDATE SKILLS: {skills_text}
CANDIDATE WORK EXPERIENCE:
{work_text}

JOB POSTING:
Title: {job.title}
Company: {job.company}
Location: {job.location or "Not specified"}
Description: {_clean_description(job.description)}

MODEL MATCH SCORE (0-1, embedding-based semantic similarity, already
computed -- do not restate it as a percentage or invent your own number):
{match_score:.3f}

Write a short rationale (2-3 sentences, plain prose, no markdown, no
bullet points) explaining specifically why this job fits the candidate's
{track.track_name} track, referencing real, specific overlaps between
the job posting and the candidate's actual skills or work history above.
If the overlap is genuinely thin, say so plainly rather than manufacturing
enthusiasm -- a honest "this is a stretch because X, but Y is relevant" is
more useful than false confidence. Do not invent any skill, employer, or
qualification not listed above. Do not address the candidate directly
("you") -- write in third person as a neutral note, e.g. "This role aligns
with James's ... because ...".

Respond with ONLY the rationale text -- no preamble, no restating the job
title, no code fences."""


def generate_match_rationale(
    profile: FullProfile,
    track: CVTrack,
    job: Job,
    match_score: float,
) -> str:
    """Full pipeline: build prompt -> call LLM -> return plain rationale text.

    Uses GROQ_MODEL_FAST (llama-3.1-8b-instant) rather than the default
    GROQ_MODEL -- 500,000 tokens/day free-tier budget vs 100,000 (confirmed
    live 2026-07-20), and a 2-3 sentence rationale grounded in facts already
    laid out explicitly in the prompt doesn't need 70b-level reasoning to
    get right. Screening answers and cover letters stay on GROQ_MODEL since
    that quality/quota tradeoff is different for longer, more consequential
    generated text.

    Raises generation.llm_client.LLMError on API failure -- callers (e.g.
    a backfill script processing hundreds of matches) should catch this
    per-row so one bad Groq response doesn't abort an entire run.
    """
    prompt = build_rationale_prompt(profile, track, job, match_score)
    raw_response = generate_text(prompt, temperature=0.5, model=GROQ_MODEL_FAST)
    return raw_response.strip()
