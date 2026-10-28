from __future__ import annotations

import streamlit as st

from src.agents import correction as C
from src.agents.validation import apply_answers
from src.models.paths import describe_path
from src.ui import state as S
from src.ui.components import badge, diff_html, step_header
from src.ui.steps.common import nav_buttons


def _act(cid: str, action: str) -> None:
    items = S.corrections()
    c = next((x for x in items if x.id == cid), None)
    if c is None:
        return
    p = S.profile()
    prev = c.status
    if action == "accept":
        p2, ok, msg = C.accept(p, c)
        if ok:
            c.status = "accepted"
    elif action == "reject":
        if c.status in ("applied", "accepted"):
            p2, ok, msg = C.revert(p, c)
        else:
            p2, ok, msg = p, True, "Suggestion dismissed."
        if ok:
            c.status = "rejected"
            st.session_state.rejected = sorted(set(st.session_state.rejected) | {c.signature()})
    else:
        return
    if ok:
        st.session_state.undo_stack.append({"id": cid, "prev": prev, "action": action})
        S.set_profile(p2)
        st.session_state.checked_fields[c.path] = c.original if c.status == "rejected" else c.corrected
    S.save_corrections(items)
    S.note(msg, "success" if ok else "warning")


def _undo() -> None:
    stack = st.session_state.undo_stack
    if not stack:
        return
    last = stack.pop()
    items = S.corrections()
    c = next((x for x in items if x.id == last["id"]), None)
    if c is None:
        return
    p = S.profile()
    if last["prev"] in ("applied", "accepted"):
        p2, ok, msg = C.accept(p, c)      # re-apply the correction
    else:
        p2, ok, msg = C.revert(p, c) if c.status == "accepted" else (p, True, "")
    if ok:
        c.status = last["prev"]
        st.session_state.rejected = [s for s in st.session_state.rejected if s != c.signature()]
        S.set_profile(p2)
        S.save_corrections(items)
        S.note("Undone.", "success")
    else:
        S.note(msg, "warning")


def _accept_all_pending() -> None:
    for c in S.corrections():
        if c.status == "pending":
            _act(c.id, "accept")


def render() -> None:
    step_header(2, "Review corrections", "Routine spelling, grammar and formatting fixes are applied automatically. "
                "Anything that could change a fact waits for your approval.")
    S.show_notices()
    items = S.corrections()
    pending = [c for c in items if c.status == "pending"]
    applied = [c for c in items if c.status in ("applied", "accepted")]
    rejected = [c for c in items if c.status == "rejected"]
    top = st.columns([2, 1, 1])
    top[0].markdown(badge("pending", f"{len(pending)} awaiting you") + badge("applied", f"{len(applied)} applied")
                    + badge("rejected", f"{len(rejected)} rejected"), unsafe_allow_html=True)
    top[1].button("↶ Undo last", on_click=_undo, disabled=not st.session_state.undo_stack, width="stretch")
    top[2].button("Accept all suggestions", on_click=_accept_all_pending, disabled=not pending, width="stretch")

    if not items:
        st.info("No corrections yet. Add information first — every new or edited sentence is checked automatically.")
    for group, title in ((pending, "Needs your confirmation"), (applied, "Applied automatically"), (rejected, "Rejected")):
        if not group:
            continue
        st.markdown(f"#### {title}")
        for c in group[:60]:
            with st.container(border=True):
                a, b = st.columns([4, 1.1])
                with a:
                    st.markdown(badge(c.status) + (badge("estimate", "AI") if c.source == "llm" else badge("rules"))
                                + f" <span class='cr-muted'>{describe_path(c.path)}</span>", unsafe_allow_html=True)
                    st.markdown(diff_html(c.original, c.corrected), unsafe_allow_html=True)
                    st.caption(c.explanation)
                with b:
                    if c.status == "pending":
                        st.button("Accept", key=f"acc_{c.id}", on_click=_act, args=(c.id, "accept"), type="primary",
                                  width="stretch")
                        st.button("Reject", key=f"rej_{c.id}", on_click=_act, args=(c.id, "reject"), width="stretch")
                    elif c.status in ("applied", "accepted"):
                        st.button("Reject", key=f"rej_{c.id}", on_click=_act, args=(c.id, "reject"),
                                  width="stretch", help="Restore your original wording")

    val = st.session_state.validation or {}
    issues = val.get("issues", [])
    st.markdown("#### Facts to confirm")
    if not issues:
        st.success("No contradictions or formatting problems found in your facts.")
    for n, i in enumerate(issues):
        with st.container(border=True):
            kind = "fail" if i["blocking"] else ("warn" if i["severity"] == "warning" else "info")
            st.markdown(badge(kind, "Required" if i["blocking"] else i["severity"].title()) + " " + i["message"],
                        unsafe_allow_html=True)
            qs = i.get("questions") or []
            if qs:
                with st.form(f"fix_{n}_{st.session_state.profile_version}"):
                    cols = st.columns(len(qs))
                    answers = {q["path"]: cols[k].text_input(q["label"], q.get("current", ""), help=q.get("help") or None)
                               for k, q in enumerate(qs)}
                    if st.form_submit_button("Save"):
                        S.set_profile(apply_answers(S.profile(), answers))
                        S.refresh_checks()
                        st.rerun()
    nav_buttons()
