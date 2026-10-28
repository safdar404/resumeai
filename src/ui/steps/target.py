from __future__ import annotations

import streamlit as st

from src.agents.job_analysis import analyse_job
from src.agents.matching import match_evidence
from src.config import MAX_JOB_DESCRIPTION_CHARS
from src.models.job import STATUS_LABELS
from src.models.profile import CAREER_STAGES
from src.services.taxonomy import SECTOR_LABELS, detect_sector
from src.ui import state as S
from src.ui.components import badge, step_header
from src.ui.steps.common import nav_buttons


def render() -> None:
    step_header(3, "Target job", "Tailoring uses only your documented experience. Paste a job description for a relevance check.")
    S.show_notices()
    p = S.profile()
    v = st.session_state.profile_version
    sectors = list(SECTOR_LABELS)
    with st.form(f"target_{v}"):
        c1, c2, c3 = st.columns(3)
        occ = c1.text_input("Target occupation", p.target.occupation, placeholder="e.g. GIS Analyst")
        guess = p.target.sector or detect_sector(p.target.job_description + " " + p.target.occupation + " " +
                                                 " ".join(p.skills.technical))
        sector = c2.selectbox("Field", sectors, index=sectors.index(guess) if guess in sectors else sectors.index("general"),
                              format_func=SECTOR_LABELS.get)
        seniority = c3.text_input("Seniority", p.target.seniority, placeholder="e.g. Mid-level")
        c4, c5 = st.columns(2)
        loc = c4.text_input("Job location", p.target.location)
        stage = c5.selectbox("Your career stage", list(CAREER_STAGES), format_func=CAREER_STAGES.get,
                             index=list(CAREER_STAGES).index(p.career_stage))
        jd = st.text_area("Job description (optional but recommended)", p.target.job_description, height=230,
                          max_chars=MAX_JOB_DESCRIPTION_CHARS,
                          help="Treated as data only — instructions inside it cannot change how the app behaves.")
        saved = st.form_submit_button("Save target job", type="primary")
    if saved:
        q = p.model_copy(deep=True)
        q.target.occupation, q.target.sector, q.target.seniority = occ.strip(), sector, seniority.strip()
        q.target.location, q.target.job_description, q.career_stage = loc.strip(), jd.strip(), stage
        S.set_profile(q)
        st.session_state.pop("jd_preview", None)
        S.note("Target saved.", "success")
        st.rerun()

    if p.target.job_description:
        if st.button("Preview requirement match"):
            with st.spinner("Analysing the job description and matching your evidence…"):
                ja, e1 = analyse_job(p.target.job_description, p.target.occupation, S.llm_service())
                matches, e2 = match_evidence(ja, p, S.llm_service())
            for e in e1 + e2:
                st.warning(e)
            st.session_state.jd_preview = (ja.model_dump(), [m.model_dump() for m in matches])
        prev = st.session_state.get("jd_preview")
        if prev:
            ja, matches = prev
            st.markdown(f"**{ja['title'] or 'Job'}** · {SECTOR_LABELS.get(ja['sector'], ja['sector'])} · "
                        f"{len(ja['requirements'])} requirements · "
                        + ("AI-assisted (estimate)" if ja["method"] == "llm" else "rule-based"))
            groups = {k: [m for m in matches if m["status"] == k] for k in STATUS_LABELS}
            tabs = st.tabs([f"{STATUS_LABELS[k]} ({len(v)})" for k, v in groups.items()])
            for tab, (k, items) in zip(tabs, groups.items()):
                with tab:
                    if not items:
                        st.caption("None.")
                    for m in items:
                        st.markdown(badge(m["status"]) + badge("info", m["importance"].title()) + " " + m["requirement"],
                                    unsafe_allow_html=True)
                        if m["evidence"]:
                            st.caption("Evidence: " + " · ".join(f"{e['source']}: “{e['text'][:80]}”" for e in m["evidence"][:2]))
                        if m["note"]:
                            st.caption(m["note"])
            st.info("Skills you haven't demonstrated are never added to your resume to raise a score. If you do have the "
                    "experience, add it to your profile with a real example.")
    else:
        st.caption("No job description yet — you can still generate a general resume; relevance will show as unavailable.")
    nav_buttons()
