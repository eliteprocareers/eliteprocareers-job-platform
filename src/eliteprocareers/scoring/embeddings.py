"""Embedding-based similarity scoring between a candidate profile and a job.

Uses a local sentence-transformers model — no API calls, no cost, fast
enough to run per-track per-job. This module only computes a raw similarity
score; it does not write to the database and does not generate rationale
text (that's generation/match_rationale.py, using Groq).
"""
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from functools import lru_cache

import torch
from sentence_transformers import SentenceTransformer, util

from eliteprocareers.profiles.models import CVTrack, FullProfile
from eliteprocareers.text_utils import clean_html_text

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model once and reuse it across calls.

    Loading takes ~1-2s; we don't want to pay that cost on every
    single job comparison.
    """
    return SentenceTransformer(_MODEL_NAME)


def build_role_text(track: CVTrack) -> str:
    """Text built purely from the track's target roles.

    Kept separate from experience text so it can be embedded and
    weighted independently — this is the strongest signal for *which*
    track a job matches, and shouldn't get diluted by long work
    history text.
    """
    if not track.target_roles:
        return track.track_name
    return "Target roles: " + ", ".join(track.target_roles)


def build_experience_text(profile: FullProfile) -> str:
    """Text built from skills, work history, and summary.

    Broader context about the candidate that isn't track-specific.
    """
    parts: list[str] = []

    skill_names = [cs.skill_name for cs in profile.skills if cs.skill_name]
    if skill_names:
        parts.append("Skills: " + ", ".join(skill_names))

    for exp in profile.work_experience:
        parts.append(f"{exp.title} at {exp.company}. {exp.description or ''}".strip())

    if profile.profile.summary:
        parts.append(profile.profile.summary)

    return " | ".join(p for p in parts if p)


_MAX_JOB_DESCRIPTION_CHARS = 800


def build_job_title_text(title: str, company: str) -> str:
    """Short, low-noise text for the job's title + company."""
    return f"{title} at {company}".strip()


def build_job_description_text(description: str | None) -> str:
    """Cleaned, capped text for the job's description body.

    HTML-stripped via the shared clean_html_text() helper (previously
    only applied to rationale prompts, not scoring -- v13 finding: raw
    HTML markup was going into the embedding for every job, adding noise
    on top of the discrimination issue below). The char cap is NOT the
    fix by itself -- all-MiniLM-L6-v2 truncates at ~256 tokens regardless,
    so this alone doesn't guarantee removing any specific passage. It's
    kept to strip boilerplate/EEO tail text and keep encode() calls cheap.
    The real fix is job_title_weight below.
    """
    return clean_html_text(description, max_chars=_MAX_JOB_DESCRIPTION_CHARS)


def build_job_text(title: str, company: str, description: str | None) -> str:
    """Flatten a job posting into text suitable for embedding.

    Kept for backward compatibility / callers that want a single blob
    (e.g. debugging, logging). Matching itself should use
    build_job_title_text() + build_job_description_text() separately via
    compute_match_score()'s job_title_weight, not this function -- see
    v13 handover for why (concatenated text let long descriptions
    dominate the job embedding regardless of relevance).
    """
    return f"{title} at {company}. {description or ''}".strip()


def compute_match_score(
    profile: FullProfile,
    track: CVTrack,
    job_title_text: str,
    job_description_text: str,
    role_weight: float = 0.7,
    job_title_weight: float = 0.6,
) -> float:
    """Weighted cosine similarity between a candidate (profile + track) and a job.

    Both sides of the comparison use the same pattern: embed sub-parts
    separately, then combine as a weighted average, rather than
    concatenating everything into one blob. Text repetition (a long work
    history, or a long job description) otherwise silently dominates a
    single combined embedding regardless of relevance.

    - role_weight (candidate side, unchanged since v9): target roles vs.
      general skills/experience. Default 0.7 favors target roles.
    - job_title_weight (NEW v13): job title+company vs. job description.
      Default 0.6 favors the title. v13 finding: a verbose job
      description can be saturated with generic role-adjacent vocabulary
      (e.g. an insurance "product development" posting reusing "product
      management/governance" language) that inflates similarity against
      an unrelated track's target roles, independent of the job's actual
      title or domain. This was misdiagnosed across 3 earlier sessions
      (v10-v12) as a title problem. UNVERIFIED against the live
      model/data as of this commit -- run the verification script in the
      v13 handover before trusting this weight or merging to main.
    """
    model = _get_model()

    role_text = build_role_text(track)
    experience_text = build_experience_text(profile)

    role_emb = model.encode(role_text, convert_to_tensor=True)
    experience_emb = model.encode(experience_text, convert_to_tensor=True)
    job_title_emb = model.encode(job_title_text, convert_to_tensor=True)
    job_description_emb = model.encode(job_description_text, convert_to_tensor=True)

    role_emb = torch.nn.functional.normalize(role_emb, dim=0)
    experience_emb = torch.nn.functional.normalize(experience_emb, dim=0)
    job_title_emb = torch.nn.functional.normalize(job_title_emb, dim=0)
    job_description_emb = torch.nn.functional.normalize(job_description_emb, dim=0)

    combined_emb = role_weight * role_emb + (1 - role_weight) * experience_emb
    combined_emb = torch.nn.functional.normalize(combined_emb, dim=0)

    combined_job_emb = (
        job_title_weight * job_title_emb
        + (1 - job_title_weight) * job_description_emb
    )
    combined_job_emb = torch.nn.functional.normalize(combined_job_emb, dim=0)

    similarity = util.cos_sim(combined_emb, combined_job_emb).item()
    return max(0.0, similarity)
