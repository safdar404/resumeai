from __future__ import annotations

import streamlit as st

from src.graph.runner import WorkflowError
from src.templates.registry import get_template
from src.ui import state as S
from src.ui.components import badge, score_ring, step_header
from src.ui.steps.common import nav_buttons


def _clarification(payload: dict) -> None:
    st.warning("I need a few answers before writing your resume. Nothing will be guessed.")
    issues = payload.get("issues", [])
    answerable = [i for i in issues if i.get("questions") and not i.get("action_only")]
    action = [i for i in issues if i.get("action_only")]
    for i in action:
        st.error(i["message"])
    if action:
        st.button("Go to Add information", on_click=S.goto, args=(1,))
    with st.form("clarify"):
        answers = {}
        for i in answerable:
            st.markdown(f"**{i['message']}**")
            cols = st.columns(len(i["questions"]))
            for k, q in enumerate(i["questions"]):
                answers[q["path"]] = cols[k].text_input(q["label"], q.get("current", ""), help=q.get("help") or None,
                                                        key=f"cl_{q['path']}")
        c1, c2 = st.columns(2)
        go = c1.form_submit_button("Submit answers and continue", type="primary", disabled=not answerable)
        stop = c2.form_submit_button("Cancel")
    if go:
        try:
            with st.spinner("Continuing…"):
                S.resume_generate(answers)
        except WorkflowError as exc:
            st.error(str(exc))
            return
        st.rerun()
    if stop:
        S.resume_generate({"__cancel__": True})
        st.session_state.interrupt = None
        st.rerun()


def render() -> None:
    step_header(5, "Generate", "The agent workflow validates, analyses the job, matches evidence, drafts, fact-checks, "
                "plans the layout, renders and re-opens your files.")
    S.show_notices()
    ss = st.session_state
    spec = get_template(ss.template_id)
    cfg = ss.llm
    provider_line = ("Offline rules engine (no data leaves this app)" if cfg["provider"] == "none" else
                     f"{cfg['provider']} · {cfg['model']}" + ("" if cfg.get("consent") else " — consent needed (sidebar)"))
    st.markdown(badge("info", f"Template: {spec.name}") + badge("info", f"Engine: {provider_line}"), unsafe_allow_html=True)
    if cfg["provider"] != "none" and cfg.get("consent"):
        st.caption(f"🔐 Your profile, resume text and job description will be sent to {cfg['provider']} for processing.")
    if ss.interrupt:
        _clarification(ss.interrupt)
        return
    stale = ss.get("results_stale", True)
    label = "Generate resume" if not ss.results else ("Regenerate with latest changes" if stale else "Regenerate")
    if st.button(label, type="primary"):
        with st.status("Working…", expanded=True) as status:
            st.write("Running the resume workflow…")
            try:
                res = S.run_generate()
            except WorkflowError as exc:
                status.update(label="Generation needs attention", state="error")
                st.error(str(exc))
                return
            for msg in res.get("progress") or []:
                st.write("✓ " + msg)
            if res.get("interrupt"):
                status.update(label="Waiting for your answers", state="error")
            elif res.get("pdf"):
                status.update(label="Resume ready", state="complete")
            else:
                status.update(label="Stopped", state="error")
        st.rerun()
    res = ss.results
    if not res:
        st.info("Ready when you are. You can generate now and refine afterwards — your profile stays editable.")
        return
    if stale:
        st.info("Your profile or settings changed since the last generation. Regenerate to include the changes.")
    c1, c2 = st.columns([1, 1.4])
    with c1:
        sc = res["score"]
        score_ring(sc["total"], sc["max_available"], "Resume Readiness (internal assessment)")
        st.caption(sc["note"])
    with c2:
        info = res.get("render_info") or {}
        rev = res.get("review") or {}
        st.markdown(badge("pass" if not info.get("overflow") else "warn", f"{info.get('pages', '?')} page(s)")
                    + badge("info", f"{info.get('body_size', '?')} pt body")
                    + badge("pass" if rev.get("passed", True) else "warn",
                            f"Fact check: {rev.get('reverted', 0)} reverted"), unsafe_allow_html=True)
        for n in info.get("notes", []):
            st.caption("• " + n)
    with st.expander("What the workflow did"):
        for m in res.get("progress") or []:
            st.write("✓ " + m)
    nav_buttons(next_label="Edit & preview")
