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


def open_profile_section(section: str) -> None:
    """Jump from a validation block straight to the appropriate editable tab."""
    from src.models.profile import Education, Experience, Project
    ss = st.session_state
    if ss.interrupt:
        ss.runner.reset()
        ss.interrupt = None
    p = S.profile().model_copy(deep=True)
    tab = {'experience': 'Experience', 'education': 'Education & skills', 'projects': 'Projects & more'}[section]
    field, factory = {'experience': ('experience', Experience), 'education': ('education', Education),
                      'projects': ('projects', Project)}[section]
    if not getattr(p, field):
        getattr(p, field).append(factory())
        S.set_profile(p)
    ss.entry_mode = 'Form'
    ss.entry_mode_ctl = 'Form'
    ss.profile_form_tab = tab
    ss.profile_form_tab_version = ss.get('profile_form_tab_version', 0) + 1
    ss.profile_return_step = 5
    S.goto(1)


def nav_top() -> None:
    """Always rendered before page bodies, including early-return/error states."""
    step = st.session_state.step
    if step == 0:
        return
    left, right = st.columns([1, 1])
    left.button('← Back to ' + S.STEPS[step - 1], on_click=S.goto, args=(step - 1,),
                key=f'top_back_{step}')
    if step == 1 and st.session_state.get('profile_return_step') == 5:
        right.button('Return to Generate →', on_click=S.goto, args=(5,), key='return_generate_top')
        st.caption('Save the role, qualification or project details first, then return to Generate.')
