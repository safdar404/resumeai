from __future__ import annotations

import streamlit as st

from src.models.paths import PathError, set_path
from src.models.profile import CandidateProfile
from src.models.resume import ResumeDocument
from src.rendering.export_validation import page_images
from src.ui import state as S
from src.ui.components import badge, step_header
from src.ui.steps.common import nav_buttons


def _preview(pdf: bytes) -> None:
    for i, img in enumerate(page_images(pdf, zoom=1.25)):
        st.image(img, caption=f"Page {i + 1}", width="stretch")


def render() -> None:
    step_header(6, "Edit", "Fine-tune wording and sections, then re-render. To add new facts, update your profile — "
                "the resume is always built from it.")
    S.show_notices()
    res = st.session_state.results
    if not res:
        st.info("Generate a resume first.")
        nav_buttons(next_label=None)
        return
    doc = ResumeDocument.model_validate(res["draft"])
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        edited_paths = set(doc.user_edited_paths)
        with st.form("edit_doc"):
            st.markdown("**Headline**")
            headline = st.text_input("Headline", doc.headline, label_visibility="collapsed")
            for sec in doc.sections:
                if not sec.text and not sec.entries and not sec.items:
                    continue
                with st.expander(f"{sec.title}", expanded=sec.key in ("summary", "experience")):
                    sec.enabled = st.checkbox("Show this section", sec.enabled, key=f"en_{sec.key}")
                    if sec.kind == "text":
                        new = st.text_area("Text", sec.text, key=f"tx_{sec.key}", height=110)
                        if new != sec.text:
                            sec.text = new.strip(); edited_paths.add("summary")
                    for ei, en in enumerate(sec.entries):
                        st.markdown(f"**{en.heading}** — {en.subheading}")
                        keep = []
                        for bi, (b, src) in enumerate(zip(en.bullets, en.bullet_sources or [""] * len(en.bullets))):
                            c1, c2 = st.columns([8, 1])
                            nb = c1.text_area(f"Point {bi + 1}", b, key=f"b_{sec.key}_{ei}_{bi}", height=68,
                                              label_visibility="collapsed")
                            show = c2.checkbox("Show", True, key=f"s_{sec.key}_{ei}_{bi}")
                            if show and nb.strip():
                                if nb.strip() != b:
                                    edited_paths.add(src)
                                keep.append((nb.strip(), src))
                        en.bullets = [k[0] for k in keep]
                        en.bullet_sources = [k[1] for k in keep]
            go = st.form_submit_button("Apply edits & re-render", type="primary")
        if go:
            doc.headline = headline.strip()
            doc.user_edited_paths = sorted(edited_paths)
            with st.spinner("Fact-checking edits and re-rendering…"):
                S.run_rerender(doc.model_dump())
            st.rerun()
        rev = res.get("review") or {}
        if rev.get("findings"):
            with st.expander(f"Fact-check findings ({len(rev['findings'])})", expanded=True):
                for f in rev["findings"]:
                    st.markdown(badge("warn" if f["action"] == "flagged" else "info",
                                      "Please confirm" if f["action"] == "flagged" else "Reverted") + f" **{f['location']}**",
                                unsafe_allow_html=True)
                    st.caption(f"“{f['text'][:140]}” — {'; '.join(f['problems'])}")
        sugg = doc.suggestions
        if sugg:
            with st.expander(f"Evidence-based suggestions ({len(sugg)})"):
                st.caption("Add measurable results only if you know them. Nothing here is filled in for you.")
                v = st.session_state.profile_version
                for k, s in enumerate(sugg[:12]):
                    st.markdown(f"{badge('info', s.kind.title())} {s.question}", unsafe_allow_html=True)
                    if s.kind == "metric" and s.path:
                        with st.form(f"sug_{k}_{v}"):
                            txt = st.text_input("Update this point in your profile", s.text)
                            if st.form_submit_button("Save to profile") and txt.strip() and txt.strip() != s.text:
                                data = S.profile().model_dump()
                                try:
                                    set_path(data, s.path, txt.strip())
                                    S.set_profile(CandidateProfile.model_validate(data))
                                    S.refresh_checks()
                                    S.note("Saved to your profile — regenerate to include it.", "success")
                                except PathError:
                                    S.note("That point no longer exists in your profile.", "warning")
                                st.rerun()
    with right:
        st.markdown("**Preview**")
        if res.get("ats_pdf"):
            if "pv_which" not in st.session_state:
                st.session_state.pv_which = "Designed"
            which = st.segmented_control("Version", ["Designed", "Parsing-friendly"], key="pv_which")
            _preview(res["ats_pdf"] if which == "Parsing-friendly" else res["pdf"])
        else:
            _preview(res["pdf"])
    nav_buttons(next_label="Validate")
