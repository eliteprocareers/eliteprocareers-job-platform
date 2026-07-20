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

from eliteprocareers.generation.llm_client import generate_text
from eliteprocareers.jobs.models import Job
from eliteprocareers.profiles.models import CVTrack, FullProfile


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
Description: {job.description or "Not provided"}

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

    Raises generation.llm_client.LLMError on API failure -- callers (e.g.
    a backfill script processing hundreds of matches) should catch this
    per-row so one bad Groq response doesn't abort an entire run.
    """
    prompt = build_rationale_prompt(profile, track, job, match_score)
    raw_response = generate_text(prompt, temperature=0.5)
    return raw_response.strip()
