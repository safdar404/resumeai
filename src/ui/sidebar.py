from __future__ import annotations

import streamlit as st

from src.config import PROVIDERS
from src.security.credentials import check_api_key, mask
from src.services.llm import LLMSettings, build_service
from src.ui import state as S
from src.ui.components import badge, progress_bar
from src.ui.theme import logo_markup


def _nav_changed() -> None:
    st.session_state.step = S.STEPS.index(st.session_state.nav_radio)


def _clear() -> None:
    S.reset_session()
    st.session_state.cleared = True


def render() -> None:
    ss = st.session_state
    if "agent_destination" in ss:
        S.goto(ss.pop("agent_destination"))
    with st.sidebar:
        st.markdown('<div class="cr-brand">' + logo_markup() + '<div><h1>CareerRainbow AI</h1>'
                    '<p>Agentic Resume Copilot</p></div></div><div class="cr-stripe"></div>',
                    unsafe_allow_html=True)
        def open_copilot():
            ss.entry_mode = "Chat"
            ss.entry_mode_ctl = "Chat"
            S.goto(1)
        st.button("✦ Open resume copilot", on_click=open_copilot, type="primary", width="stretch")
        if "nav_radio" not in ss:
            ss.nav_radio = S.STEPS[ss.step]
        val = ss.validation or {}
        progress_bar(val.get("completion", 0), "Profile")
        st.radio("Steps", S.STEPS, key="nav_radio", on_change=_nav_changed,
                 format_func=lambda s: f"{S.STEPS.index(s) + 1}. {s}")
        st.divider()
        with st.expander("⚙️ AI provider", expanded=False):
            cfg = ss.llm
            provs = list(PROVIDERS)
            prov = st.selectbox("Provider", provs, index=provs.index(cfg["provider"]),
                                format_func=lambda k: PROVIDERS[k]["label"])
            if prov != cfg["provider"]:
                cfg.update(provider=prov, model=PROVIDERS[prov]["default_model"], verified=None, consent=False)
                st.rerun()
            if prov != "none":
                cfg["model"] = st.text_input("Model", cfg["model"])
                if prov == "openai_compatible":
                    cfg["base_url"] = st.text_input("Base URL", cfg.get("base_url", ""), placeholder="https://api.groq.com/openai/v1")
                key_in = st.text_input("API key (kept only in this session's memory)", type="password",
                                       value=cfg.get("session_key", ""), help="Or configure it in Streamlit secrets.")
                if key_in != cfg.get("session_key", ""):
                    cfg["session_key"] = key_in
                    cfg["verified"] = None
                key, source = S.resolve_key()
                st.caption(f"Key: {mask(key)} · source: {source}")
                if key:
                    chk = check_api_key(key)
                    for prob in chk.problems:
                        st.error(prob + " The key was not modified — please fix it at its source.")
                cfg["consent"] = st.checkbox(
                    f"I agree that my profile, resume text and job descriptions are sent to {PROVIDERS[prov]['label']} "
                    "for processing.", value=cfg.get("consent", False))
                if st.button("Test connection", width="stretch"):
                    svc, err = build_service(LLMSettings(provider=prov, model=cfg["model"], api_key=key,
                                                         base_url=cfg.get("base_url", "")))
                    if err:
                        cfg["verified"] = (False, err)
                    else:
                        with st.spinner("Contacting provider…"):
                            cfg["verified"] = svc.test_connection()
                if cfg.get("verified"):
                    ok, msg = cfg["verified"]
                    (st.success if ok else st.error)(msg)
            else:
                st.caption("Offline mode uses deterministic rules for extraction, correction, matching and drafting. "
                           "No data leaves the app.")
        mode = "Offline rules" if ss.llm["provider"] == "none" else (
            f"AI: {ss.llm['provider']}" + ("" if ss.llm.get("consent") else " (consent needed)"))
        st.markdown(badge("rules" if ss.llm["provider"] == "none" else "estimate", mode), unsafe_allow_html=True)
        with st.expander("🔒 Privacy", expanded=False):
            st.markdown("- Your data stays in this browser session's server memory and is **not stored** after the "
                        "session ends.\n- Uploaded files are read in memory; no copies are written to disk.\n"
                        "- With an AI provider enabled (and only after your consent), text is sent to that provider "
                        "under its terms.\n- API keys are never logged or displayed.")
            st.button("🧹 Clear my session and files", on_click=_clear, width="stretch", type="primary")
        st.caption("Your story. Your next opportunity. ✦")
