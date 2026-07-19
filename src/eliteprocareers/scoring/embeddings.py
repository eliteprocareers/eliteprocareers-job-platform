"""Embedding-based similarity scoring between a candidate profile and a job.

Uses a local sentence-transformers model — no API calls, no cost, fast
enough to run per-track per-job. This module only computes a raw similarity
score; it does not write to the database and does not generate rationale
text (that's a separate module using Gemini).
"""
from functools import lru_cache

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


def build_profile_text(profile: FullProfile, track: CVTrack) -> str:
    """Flatten a candidate's profile + track into a single text block
    suitable for embedding.

    Weighted toward what the track is targeting: target_roles are
    repeated to nudge the embedding toward that framing, since a
    candidate applying under different tracks should score differently
    against the same job.
    """
    parts: list[str] = []

    if track.target_roles:
        parts.append("Target roles: " + ", ".join(track.target_roles))
        parts.append(" ".join(track.target_roles))  # light repetition/emphasis

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


def compute_match_score(profile_text: str, job_text: str) -> float:
    """Cosine similarity between profile and job text, as a 0-1 float.

    sentence-transformers embeddings from this model are roughly on the
    same scale as cosine similarity already, but util.cos_sim guarantees
    the [-1, 1] range; we clamp to [0, 1] since negative similarity isn't
    meaningful for job matching.
    """
    model = _get_model()
    profile_emb = model.encode(profile_text, convert_to_tensor=True)
    job_emb = model.encode(job_text, convert_to_tensor=True)
    similarity = util.cos_sim(profile_emb, job_emb).item()
    return max(0.0, similarity)
