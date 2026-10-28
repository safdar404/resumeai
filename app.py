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
except Exception:  # last-resort guard: never show a stack trace with user data
    logging.getLogger("careerrainbow").exception("Unhandled UI error")
    st.error("Something went wrong on this step. Your profile is still in this session — try again, or go back a step. "
             "If it persists, download your profile JSON from the Download step.")
