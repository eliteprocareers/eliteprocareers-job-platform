"""
ElitePro AI Platform — Internal Dashboard (Streamlit)

First working UI for viewing scored job matches, replacing hand-run
diagnostic scripts. This is the "fast internal dashboard, speed over
polish" build discussed in the session-handover chain. Streamlit calls
the existing eliteprocareers modules in-process. No REST API layer
exists or is introduced here -- a formal API only earns its cost once
something *external* needs to call the backend (a separate frontend,
a mobile app), which is Phase 3, not this.

Run locally:
    streamlit run dashboard/streamlit_app.py
"""

from __future__ import annotations

import os

import streamlit as st

for _key in (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
):
    if _key in st.secrets and _key not in os.environ:
        os.environ[_key] = st.secrets[_key]

from eliteprocareers.db.auth import AuthError, sign_in
from eliteprocareers.db.client import SupabaseClient
from eliteprocareers.generation.cv_tailoring import CVGenerationError, generate_tailored_cv
from eliteprocareers.jobs.models import Job
from eliteprocareers.matching.repository import UserJobMatchRepository
from eliteprocareers.profiles.document_repository import DocumentRepository
from eliteprocareers.profiles.models import CVContent
from eliteprocareers.profiles.repository import ProfileRepository
from eliteprocareers.profiles.track_repository import TrackRepository

st.set_page_config(page_title="ElitePro — Matches", layout="wide")


def _do_login(email: str, password: str) -> None:
    try:
        session = sign_in(email, password)
    except AuthError as e:
        st.session_state["auth_error"] = str(e)
        return
    st.session_state["access_token"] = session["access_token"]
    st.session_state["user_id"] = session["user"]["id"]
    st.session_state.pop("auth_error", None)


def render_cv(content_json: str) -> None:
    """Render a CVContent JSON string as a formatted CV instead of raw JSON."""
    try:
        cv = CVContent.from_json(content_json)
    except Exception as e:
        st.error(f"Couldn't parse saved CV content: {e}")
        st.code(content_json, language="json")
        return

    st.markdown("#### Summary")
    st.write(cv.summary)

    if cv.skills:
        st.markdown("#### Skills")
        st.write(" · ".join(cv.skills))

    if cv.work_experience:
        st.markdown("#### Work Experience")
        for entry in cv.work_experience:
            st.markdown(f"**{entry.title}** — {entry.company}  \n*{entry.dates}*")
            for bullet in entry.bullets:
                st.markdown(f"- {bullet}")

    if cv.education:
        st.markdown("#### Education")
        for e in cv.education:
            st.markdown(f"- {e}")

    if cv.certifications:
        st.markdown("#### Certifications")
        for c in cv.certifications:
            st.markdown(f"- {c}")


if "access_token" not in st.session_state:
    st.title("ElitePro — Sign in")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        _do_login(email, password)
        st.rerun()
    if "auth_error" in st.session_state:
        st.error(st.session_state["auth_error"])
    st.stop()


db = SupabaseClient(access_token=st.session_state["access_token"])
user_id = st.session_state["user_id"]

with st.sidebar:
    st.write(f"Signed in as `{user_id}`")
    if st.button("Sign out"):
        st.session_state.clear()
        st.rerun()

st.title("Job Matches")

track_repo = TrackRepository(db)
tracks = track_repo.list_tracks(user_id)

if not tracks:
    st.warning("No CV tracks found for this account.")
    st.stop()

track_names = {t.track_name: t for t in tracks}
selected_name = st.selectbox("CV track", list(track_names.keys()))
track = track_names[selected_name]

col_a, col_b = st.columns(2)
with col_a:
    min_score = st.slider("Minimum match score", 0.0, 1.0, 0.5, 0.05)
with col_b:
    top_n = st.number_input("Show top N", min_value=5, max_value=200, value=25, step=5)

match_repo = UserJobMatchRepository(db)
with st.spinner("Loading matches..."):
    matches = match_repo.list_matches_for_track(track.id, min_score=min_score)

st.caption(f"{len(matches)} matches at or above {min_score:.2f} for {track.track_name}")

matches = matches[: int(top_n)]

if not matches:
    st.info("No matches at this score threshold yet.")
    st.stop()

job_ids = [str(m.job_id) for m in matches]
job_rows = db.select(
    "jobs",
    params={"select": "*", "id": f"in.({','.join(job_ids)})"},
)
jobs_by_id = {row["id"]: Job.model_validate(row) for row in job_rows}

profile_repo = ProfileRepository(db)
doc_repo = DocumentRepository(db)

if "tailored_cvs" not in st.session_state:
    st.session_state["tailored_cvs"] = {}

for m in matches:
    job = jobs_by_id.get(str(m.job_id))
    if job is None:
        continue

    with st.container(border=True):
        left, right = st.columns([4, 1])
        with left:
            st.markdown(f"**{job.title}** — {job.company}")
            meta_bits = [
                bit
                for bit in (job.location, job.attributes.get("employment_type"))
                if bit
            ]
            if meta_bits:
                st.caption(" · ".join(meta_bits))
            if job.url:
                st.markdown(f"[View posting]({job.url})")
        with right:
            score_display = f"{m.match_score:.2f}" if m.match_score is not None else "—"
            st.metric("Score", score_display)

        if m.ai_rationale:
            st.write(m.ai_rationale)
        else:
            st.caption("No rationale generated yet.")

        job_key = str(job.id)
        button_col, _ = st.columns([1, 3])
        with button_col:
            generate_clicked = st.button("Generate tailored CV", key=f"gen_{job_key}")

        if generate_clicked:
            with st.spinner("Tailoring CV for this job..."):
                try:
                    full_profile = profile_repo.get_full_profile(user_id)
                    if full_profile is None:
                        st.error("No candidate profile found for this account.")
                    else:
                        job_description = getattr(job, "description", "") or ""
                        doc = generate_tailored_cv(
                            profile=full_profile,
                            track=track,
                            job_description=job_description,
                            doc_repo=doc_repo,
                        )
                        st.session_state["tailored_cvs"][job_key] = doc.content
                except CVGenerationError as e:
                    st.error(f"Couldn't generate a CV for this job: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

        if job_key in st.session_state["tailored_cvs"]:
            with st.expander("Tailored CV (latest version)", expanded=True):
                render_cv(st.session_state["tailored_cvs"][job_key])
