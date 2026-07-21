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


# Markers that typically start the role-specific portion of a Greenhouse
# (or similar ATS) job description, after a generic company-boilerplate
# intro. v15 diagnostic session: confirmed live that 13/15 sampled
# Greenhouse companies front-load 800-3000+ chars of "About Us"/mission
# copy before any role content, and _MAX_JOB_DESCRIPTION_CHARS=800 was
# truncating every one of them inside that intro -- meaning the PM/SaaS
# canary problem (and general company-clustering in match results) was
# substantially a truncation bug, not purely a title/keyword/embedding
# problem as approaches #1-#5 all assumed. See handover v16.
_ROLE_CONTENT_MARKERS = [
    "about the role", "responsibilities", "what you'll do", "what you will do",
    "what you", "who you are", "requirements", "qualifications",
]
# v15/v16 note: "the role" and "the team" were tried and dropped -- both
# are short/generic enough to match mid-sentence inside ordinary intro
# boilerplate (e.g. Cloudflare's "...shared across the team to lift
# everyone up"), causing a false-early skip that left boilerplate debris
# in the retained text. Confirmed live against the same 5 diagnostic jobs
# before landing on this list.

# Minimum character offset a marker must appear at before we treat it as
# "skip everything before this" -- avoids discarding a short, already-
# relevant opening on the rare job that leads with role content.
_MIN_INTRO_SKIP_CHARS = 150


def _skip_intro_boilerplate(text: str) -> str:
    """Slice off a leading company-boilerplate block, if detected.

    No-op (returns text unchanged) if no marker is found -- this is the
    fallback path for companies like Airbnb/Squarespace that didn't match
    any tested marker in the v15 diagnostic sample. Not a regression for
    those: behavior is identical to pre-fix.
    """
    lowered = text.lower()
    earliest = None
    for marker in _ROLE_CONTENT_MARKERS:
        idx = lowered.find(marker)
        if idx != -1 and (earliest is None or idx < earliest):
            earliest = idx
    if earliest is not None and earliest >= _MIN_INTRO_SKIP_CHARS:
        return text[earliest:]
    return text


def build_job_text(title: str, company: str, description: str | None) -> str:
    """Flatten a job posting into text suitable for embedding.

    v14 note: an earlier version of this session split title/description
    into separately-weighted embeddings (job_title_weight). REVERTED --
    live-verified to make the PM/SaaS canary problem worse (0.5677 ->
    0.7098), not better, because the job's *title* ("Assistant Manager -
    Product Development") carries the same generic "product" collision as
    the description, so upweighting title made it worse. Back to a single
    blob, but now HTML-cleaned (previously only rationale prompts were --
    raw HTML was going straight into every job's scoring embedding).
    The actual fix for the canary is industry_mismatch_penalty() below,
    which uses structured taxonomy data instead of embedding text at all.

    v15/v16 note: HTML-cleaning alone wasn't enough -- the 800-char cap
    was truncating nearly every Greenhouse job inside its company-mission
    intro before reaching any role content. _skip_intro_boilerplate() now
    runs before the cap so the retained text is actually role-specific.
    """
    clean_description = clean_html_text(description, max_chars=None)
    clean_description = _skip_intro_boilerplate(clean_description)
    if len(clean_description) > _MAX_JOB_DESCRIPTION_CHARS:
        clean_description = clean_description[:_MAX_JOB_DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "..."
    return f"{title} at {company}. {clean_description}".strip()


# Multiplicative penalty applied (post-hoc, not inside the embedding) when
# a job's structured industry tags partially overlap the track's selected
# industries but also include at least one tag the track didn't select.
# v14: root-cause fix for the PM/SaaS canary (NCBA Group, "Assistant
# Manager - Product Development") -- it passes Stage-1's industry check
# because MyJobMag tags it both "Banking & Insurance" AND "Product &
# Project Management" (track selected the latter, not the former), and
# Stage-1's ANY-overlap logic is deliberately permissive (see
# filtering.check_industry docstring) so it isn't meant to catch this.
# This operates on structured taxonomy data, not lexical/embedding
# similarity -- unlike all 4 prior PM/SaaS attempts (v10-v14), which all
# tried to fix this via text/embedding tuning and were ruled out or
# reverted. No-op (returns 1.0) whenever a job has no industry data at
# all (e.g. every current Greenhouse job) -- doesn't touch or risk
# regressing jobs the embedding-only path already scores reasonably.
_INDUSTRY_MISMATCH_PENALTY = 0.3


def compute_industry_mismatch_penalty(track: CVTrack, job) -> float:
    """Returns a multiplier in (0, 1] for job.attributes['industry'] tags
    that fall outside track.industries. 1.0 (no penalty) when there's no
    structured industry data on either side, or every job industry tag is
    already within track.industries -- only penalizes the specific
    "partially overlaps but also carries an unselected industry" case
    that lets jobs like the NCBA canary through Stage-1's intentionally
    permissive ANY-overlap check.

    UNVERIFIED against live data as of this commit's numeric value
    (0.3) -- run the updated verification script before treating this
    weight as final; the mechanism (which jobs get penalized at all) was
    confirmed live via direct Supabase query this session, but the
    specific 0.3 multiplier is a starting guess, not tuned.
    """
    if not track.industries:
        return 1.0
    job_industry = getattr(job, "attributes", {}).get("industry")
    if not job_industry:
        return 1.0
    job_industries = job_industry if isinstance(job_industry, list) else [job_industry]
    mismatched = [i for i in job_industries if i not in track.industries]
    if not mismatched:
        return 1.0
    return _INDUSTRY_MISMATCH_PENALTY


def compute_match_score(
    profile: FullProfile,
    track: CVTrack,
    job_text: str,
    role_weight: float = 0.7,
) -> float:
    """Weighted cosine similarity between a candidate (profile + track) and a job.

    Role text and experience text are embedded separately, then combined
    as a weighted average before comparing to the job. This gives target
    roles real, controllable influence instead of relying on text
    repetition, which gets diluted once work history text is long.

    role_weight controls how much target roles dominate vs. general
    skills/experience. Default 0.7 favors target roles, since which
    track a candidate is applying under should matter more than raw
    experience overlap.

    Does NOT apply compute_industry_mismatch_penalty() -- that's a
    separate, structured-data-based adjustment applied by the caller
    (matching_service.py) after this function returns, not part of the
    embedding similarity itself.
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
