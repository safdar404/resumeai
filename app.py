"""CareerRainbow AI — Agentic CV & Resume Studio (Streamlit entry point)."""
from __future__ import annotations

import logging

import streamlit as st

from src.config import APP_NAME
from src.ui import sidebar, state as S, theme
from src.ui.steps import add_info, corrections, download, edit, generate, start, target, templates_step, validate

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title=f"{APP_NAME} — Resume Studio", page_icon="🌈", layout="wide",
                   initial_sidebar_state="expanded")
theme.inject()
S.init()
sidebar.render()

if st.session_state.pop("cleared", False):
    st.success("Your session, profile and generated files were cleared from memory.")

PAGES = [start.render, add_info.render, corrections.render, target.render, templates_step.render, generate.render,
         edit.render, validate.render, download.render]

try:
    PAGES[st.session_state.step]()
except Exception as exc:  # show diagnostic location, never exception text or user data
    import traceback
    from pathlib import Path

    frames = traceback.extract_tb(exc.__traceback__)
    own = [frame for frame in frames if "/src/" in frame.filename or frame.filename.endswith("/app.py")]
    last = own[-1] if own else frames[-1]
    location = f"{Path(last.filename).name}:{last.lineno}"
    kind = type(exc).__name__
    logging.getLogger("careerrainbow").error("UI failed: type=%s location=%s", kind, location)
    st.error(f"Step {st.session_state.step + 1} stopped: {kind} at {location}. "
             "Your profile is still available in this session.")
    st.info("Please share this error code for troubleshooting. You can save your profile JSON from Step 9.")
