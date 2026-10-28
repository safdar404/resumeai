from __future__ import annotations

import json
import re

import streamlit as st

from src.ui import state as S
from src.ui.components import badge, step_header
from src.ui.steps.common import nav_buttons


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", name or "resume").strip("_")
    return s or "resume"


def render() -> None:
    step_header(8, "Download", "PDF and DOCX are generated from the same structured resume, so their content matches.")
    S.show_notices()
    res = st.session_state.results
    p = S.profile()
    base = _slug(p.full_name)
    val = st.session_state.validation or {}
    blocking = [i for i in val.get("issues", []) if i.get("blocking")]
    if blocking:
        st.error("Some required details are unresolved: " + "; ".join(i["message"] for i in blocking[:3]))
    if res and st.session_state.get("results_stale"):
        st.warning("Your profile or settings changed after these files were generated. Regenerate to include the changes.")
    if res:
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            st.markdown("**Designed version** " + badge("ats" if not res.get("ats_pdf") else "presentation"),
                        unsafe_allow_html=True)
            st.download_button("⬇ Download PDF", res["pdf"], f"{base}_Resume.pdf", "application/pdf",
                               width="stretch", type="primary")
            st.download_button("⬇ Download DOCX", res["docx"], f"{base}_Resume.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               width="stretch")
        if res.get("ats_pdf"):
            with c2, st.container(border=True):
                st.markdown("**Parsing-friendly version** " + badge("ats"), unsafe_allow_html=True)
                st.caption("Use this for online application portals.")
                st.download_button("⬇ Download PDF (parsing-friendly)", res["ats_pdf"], f"{base}_Resume_ATS.pdf",
                                   "application/pdf", width="stretch", type="primary")
                st.download_button("⬇ Download DOCX (parsing-friendly)", res["ats_docx"], f"{base}_Resume_ATS.docx",
                                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   width="stretch")
    else:
        st.info("Generate your resume to download PDF and DOCX files. You can save your profile now.")
    st.markdown("#### Save your profile")
    payload = json.dumps({"app": "CareerRainbow AI", "profile": p.model_dump()}, ensure_ascii=False, indent=2)
    st.download_button("⬇ Download profile (JSON)", payload.encode("utf-8"), f"{base}_profile.json", "application/json")
    st.caption("Re-import this file later under Add information → Upload to continue where you left off. "
               "It contains your personal details — store it safely.")
    nav_buttons(next_label=None)
