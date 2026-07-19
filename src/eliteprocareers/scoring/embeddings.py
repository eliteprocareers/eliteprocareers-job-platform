"""Embedding-based similarity scoring between a candidate profile and a job.

Uses a local sentence-transformers model — no API calls, no cost, fast
enough to run per-track per-job. This module only computes a raw similarity
score; it does not write to the database and does not generate rationale
text (that's a separate module using Gemini).
"""
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from functools import lru_cache

import torch
from sentence_transformers import SentenceTransformer, util

from eliteprocareers.profiles.models import CVTrack, FullProfile

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


def build_job_text(title: str, company: str, description: str | None) -> str:
    """Flatten a job posting into text suitable for embedding."""
    return f"{title} at {company}. {description or ''}".strip()


def compute_match_score(
    profile: FullProfile,
    track: CVTrack,
    job_text: str,
    role_weight: float = 0.6,
) -> float:
    """Weighted cosine similarity between a candidate (profile + track) and a job.

    Role text and experience text are embedded separately, then combined
    as a weighted average before comparing to the job. This gives target
    roles real, controllable influence instead of relying on text
    repetition, which gets diluted once work history text is long.

    role_weight controls how much target roles dominate vs. general
    skills/experience. Default 0.6 favors target roles, since which
    track a candidate is applying under should matter more than raw
    experience overlap.
    """
    model = _get_model()

    role_text = build_role_text(track)
    experience_text = build_experience_text(profile)

    role_emb = model.encode(role_text, convert_to_tensor=True)
    experience_emb = model.encode(experience_text, convert_to_tensor=True)
    job_emb = model.encode(job_text, convert_to_tensor=True)

    role_emb = torch.nn.functional.normalize(role_emb, dim=0)
    experience_emb = torch.nn.functional.normalize(experience_emb, dim=0)

    combined_emb = role_weight * role_emb + (1 - role_weight) * experience_emb
    combined_emb = torch.nn.functional.normalize(combined_emb, dim=0)

    similarity = util.cos_sim(combined_emb, job_emb).item()
    return max(0.0, similarity)
