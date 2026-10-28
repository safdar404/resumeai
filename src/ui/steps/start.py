from __future__ import annotations

import streamlit as st

from src.config import EXAMPLES_DIR
from src.models.profile import CAREER_STAGES, CandidateProfile
from src.ui import state as S
from src.ui.components import card, step_header


def _begin(mode: str) -> None:
    st.session_state.entry_mode = mode
    st.session_state.entry_mode_ctl = mode
    S.goto(1)


def _load_sample() -> None:
    p = CandidateProfile.model_validate_json((EXAMPLES_DIR / "sample_profile_gis.json").read_text(encoding="utf-8"))
    p.target.job_description = (EXAMPLES_DIR / "job_gis_analyst.txt").read_text(encoding="utf-8")
    S.set_profile(p)
    S.refresh_checks()
    st.session_state.entry_mode = "Form"
    st.session_state.entry_mode_ctl = "Form"
    S.note("Loaded a fictional sample candidate with a sample job description. Notice the spelling fixes waiting "
           "in Review corrections.", "success")
    S.goto(1)


def render() -> None:
    step_header(0, "Start", "Build an accurate, well-structured resume tailored to a real job — without invented claims.")
    cols = st.columns(3)
    entries = [
        ("Chat", "Build through conversation", "Answer focused questions one at a time. Type *skip* for anything optional.", "#FF4D6D"),
        ("Form", "Complete a structured form", "Fill in sections directly. Ideal if you have details ready to paste.", "#22B8F0"),
        ("Upload", "Upload an existing resume", "Text-based PDF, DOCX or TXT — or re-import a saved JSON profile.", "#9B5DE5"),
    ]
    for col, (mode, title, body, color) in zip(cols, entries):
        with col:
            card(title, f"<p>{body}</p>", accent=color)
            st.button("Start here", key=f"start_{mode}", on_click=_begin, args=(mode,), width="stretch",
                      type="primary" if mode == "Chat" else "secondary")
    st.write("")
    c1, c2 = st.columns([1.2, 1])
    with c1:
        stage = st.selectbox("Your career stage (adjusts section order and advice)", list(CAREER_STAGES),
                             format_func=CAREER_STAGES.get,
                             index=list(CAREER_STAGES).index(S.profile().career_stage), key="stage_start")
        if stage != S.profile().career_stage:
            p = S.profile().model_copy(deep=True)
            p.career_stage = stage
            S.set_profile(p)
    with c2:
        st.caption("Just exploring?")
        st.button("Load a fictional sample candidate", on_click=_load_sample, width="stretch")
    with st.expander("How CareerRainbow keeps your resume honest", expanded=False):
        st.markdown(
            "- **No invented facts.** Every generated line is checked against what you provided; unsupported numbers, "
            "tools or employers are reverted automatically.\n"
            "- **Corrections you control.** Spelling and grammar fixes are shown side by side with accept, reject and undo.\n"
            "- **Honest scoring.** The readiness score is an internal, explained assessment — not an employer's ATS score, "
            "and never a guarantee.\n"
            "- **Privacy.** Documents are processed in memory for this session only. Nothing is stored after you leave or "
            "press *Clear my session and files*. If you enable an AI provider, your text is sent to that provider.")
