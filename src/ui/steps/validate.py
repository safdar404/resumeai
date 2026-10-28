from __future__ import annotations

import streamlit as st

from src.config import READINESS_NOTE
from src.models.job import STATUS_LABELS
from src.ui import state as S
from src.ui.components import badge, score_ring, step_header
from src.ui.steps.common import nav_buttons


def _checks(title: str, rep: dict | None) -> None:
    if not rep:
        return
    st.markdown(f"**{title}**")
    for c in rep["checks"]:
        kind = "pass" if c["passed"] else ("warn" if c["severity"] != "error" else "fail")
        if c["severity"] == "info":
            kind = "info"
        st.markdown(badge(kind) + f" {c['name']}" + (f" <span class='cr-muted'>— {c['detail']}</span>" if c["detail"] else ""),
                    unsafe_allow_html=True)


def render() -> None:
    step_header(7, "Validate", "A transparent, application-specific assessment plus checks on the actual exported files.")
    S.show_notices()
    res = st.session_state.results
    if not res:
        st.info("Generate a resume first.")
        nav_buttons(next_label=None)
        return
    sc = res["score"]
    c1, c2 = st.columns([1, 2])
    with c1:
        score_ring(sc["total"], sc["max_available"], "Resume Readiness Score")
    with c2:
        st.info(READINESS_NOTE)
        if sc["max_available"] < 100:
            st.caption(f"Scored out of {sc['max_available']} because some components are unavailable (see below). "
                       "No job-specific score is invented.")
    for comp in sc["components"]:
        head = f"{comp['name']} — " + (f"{comp['points']:g} / {comp['max_points']}" if comp["available"] else "unavailable")
        with st.expander(head, expanded=bool(comp["deductions"]) and comp["key"] in ("relevance", "parsing")):
            tags = badge("estimate", "Estimate (AI-assisted)") if comp["estimate"] else badge("rules", "Deterministic")
            st.markdown(tags, unsafe_allow_html=True)
            if comp["note"]:
                st.caption(comp["note"])
            for d in comp["deductions"]:
                st.markdown(f"**−{d['points']:g}** {d['reason']}  \n<span class='cr-muted'>→ {d['fix']}</span>",
                            unsafe_allow_html=True)
            for p in comp["passed"][:8]:
                st.markdown(badge("pass") + " " + p, unsafe_allow_html=True)
    st.markdown("#### Requirement coverage")
    matches = res.get("matches") or []
    if not matches:
        st.caption("No job description supplied, so there is nothing to match against.")
    else:
        for k, lbl in STATUS_LABELS.items():
            group = [m for m in matches if m["status"] == k]
            if group:
                st.markdown(f"**{lbl}** ({len(group)})")
                for m in group:
                    st.markdown(badge(m["status"]) + " " + m["requirement"][:140], unsafe_allow_html=True)
    st.markdown("#### File checks")
    rep = res.get("export_report") or {}
    a, b = st.columns(2)
    with a:
        _checks("PDF", rep.get("pdf"))
    with b:
        _checks("DOCX", rep.get("docx"))
    if rep.get("ats_pdf"):
        _checks("Parsing-friendly PDF", rep["ats_pdf"])
    info = res.get("render_info") or {}
    if info.get("overflow"):
        st.warning("Your content exceeds the page target at a readable size. Nothing was removed. Options:")
        for s in info.get("suggestions", []):
            st.markdown("- " + s)
    val = st.session_state.validation or {}
    if val.get("missing_for_export"):
        st.caption("Optional items still missing: " + ", ".join(val["missing_for_export"]))
    nav_buttons(next_label="Download")
