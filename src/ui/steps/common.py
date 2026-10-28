from __future__ import annotations

import streamlit as st

from src.ui import state as S


def nav_buttons(back: bool = True, next_label: str | None = "Continue", next_disabled: bool = False) -> None:
    st.write("")
    c1, _, c3 = st.columns([1, 3, 1.3])
    step = st.session_state.step
    if back and step > 0:
        c1.button("← Back", on_click=S.goto, args=(step - 1,), width="stretch", key=f"back_{step}")
    if next_label and step < len(S.STEPS) - 1:
        c3.button(f"{next_label} →", on_click=S.goto, args=(step + 1,), type="primary", width="stretch",
                  disabled=next_disabled, key=f"next_{step}")
