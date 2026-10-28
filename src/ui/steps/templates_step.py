from __future__ import annotations

import pandas as pd
import streamlit as st

from src.agents.drafting import build_document
from src.config import EXAMPLES_DIR
from src.models.profile import CandidateProfile
from src.rendering.export_validation import page_images
from src.rendering.fonts import FONTS
from src.rendering.pdf_renderer import render_pdf
from src.services.taxonomy import detect_sector
from src.templates.registry import (SECTION_TITLES, TEMPLATE_MAP, TEMPLATES, RenderOptions, get_template,
                                    recommended_templates)
from src.ui import state as S
from src.ui.components import badge, step_header
from src.ui.steps.common import nav_buttons


@st.cache_data(show_spinner=False, max_entries=32)
def thumbnail(template_id: str) -> bytes:
    """Rendered from the fictional sample candidate (shared, non-personal data)."""
    p = CandidateProfile.model_validate_json((EXAMPLES_DIR / "sample_profile_gis.json").read_text(encoding="utf-8"))
    spec = get_template(template_id)
    opts = RenderOptions(page_target="1" if "1" in spec.page_options else spec.page_options[0])
    doc = build_document(p, None, [], spec, opts)
    pdf, _ = render_pdf(doc, spec, opts)
    return page_images(pdf, zoom=0.55, max_pages=1)[0]


def _select(tid: str) -> None:
    st.session_state.template_id = tid
    st.session_state.results_stale = True
    spec = get_template(tid)
    opts = RenderOptions.model_validate(st.session_state.options)
    if opts.page_target not in spec.page_options:
        opts.page_target = spec.default_pages  # type: ignore[assignment]
    opts.font = None
    opts.accent = None
    st.session_state.options = opts.model_dump()


def _customise() -> None:
    spec = get_template(st.session_state.template_id)
    opts = RenderOptions.model_validate(st.session_state.options)
    st.markdown(f"#### Customise · {spec.name}")
    with st.form("customise"):
        c1, c2, c3 = st.columns(3)
        size = c1.radio("Paper", ["A4", "Letter"], index=["A4", "Letter"].index(opts.page_size), horizontal=True)
        labels = {"1": "1 page", "2": "2 pages", "academic": "Academic CV (no limit)"}
        targets = spec.page_options
        target = c2.radio("Length target", targets, index=targets.index(opts.page_target) if opts.page_target in targets else 0,
                          format_func=labels.get, horizontal=True)
        align = c3.radio("Text alignment", ["left", "justify"], index=["left", "justify"].index(opts.alignment),
                         horizontal=True, help="Left is easiest to read. Justified text can leave gaps on short lines.")
        fonts = list(FONTS)
        font = c1.selectbox("Font", fonts, index=fonts.index(opts.font or spec.font), format_func=lambda k: FONTS[k]["label"])
        accent = c2.color_picker("Accent colour", opts.accent or spec.accent)
        body = c3.select_slider("Body text size (pt)", [10.5, 11.0], value=opts.body_size or spec.body_size)
        dfmt = c1.radio("Date style", ["short", "numeric"], index=["short", "numeric"].index(opts.date_format),
                        format_func={"short": "Mar 2021", "numeric": "03/2021"}.get, horizontal=True)
        mb = c2.number_input("Max points per role (0 = all)", 0, 10, opts.max_bullets_per_role,
                             help="A deliberate choice you make — the app never drops content silently.")
        tailor = c3.toggle("Order points by job relevance", opts.tailor_bullet_order)
        order = opts.section_order or spec.section_order
        df = pd.DataFrame({"Section": [SECTION_TITLES[k] for k in order], "Show": [k not in opts.disabled_sections for k in order],
                           "Position": list(range(1, len(order) + 1)), "key": order})
        ed = st.data_editor(df, hide_index=True, width="stretch", disabled=["Section", "key"],
                            column_config={"key": None, "Position": st.column_config.NumberColumn(min_value=1, max_value=20, step=1)})
        if st.form_submit_button("Apply settings", type="primary"):
            ed = ed.sort_values("Position", kind="stable")
            new = RenderOptions(page_size=size, page_target=target, font=font if font != spec.font else None,
                                accent=accent if accent.upper() != spec.accent.upper() else None, body_size=body,
                                alignment=align, date_format=dfmt, max_bullets_per_role=int(mb),
                                disabled_sections=[k for k, s in zip(ed["key"], ed["Show"]) if not s],
                                section_order=list(ed["key"]), tailor_bullet_order=tailor)
            st.session_state.options = new.model_dump()
            st.session_state.results_stale = True
            st.toast("Settings applied — regenerate to see them.", icon="🎨")
    if st.button("Reset to template defaults"):
        _select(spec.id)
        st.rerun()


def render() -> None:
    step_header(4, "Choose template", "Fifteen designs from one shared, tested renderer. Exported resumes stay restrained "
                "and professional; colour is a quiet accent.")
    p = S.profile()
    sector = p.target.sector or detect_sector(p.target.job_description + " " + p.target.occupation)
    rec = recommended_templates(sector, p.career_stage)
    cur = st.session_state.template_id
    st.markdown("Recommended for you: " + " ".join(badge("ats" if not TEMPLATE_MAP[r].presentation_oriented else "presentation",
                                                       TEMPLATE_MAP[r].name) for r in rec), unsafe_allow_html=True)
    if "tmpl_filter" not in st.session_state:
        st.session_state.tmpl_filter = "All"
    filt = st.segmented_control("Show", ["All", "Recommended", "Parsing-friendly", "Presentation"], key="tmpl_filter")
    items = TEMPLATES
    if filt == "Recommended":
        items = [TEMPLATE_MAP[r] for r in rec]
    elif filt == "Parsing-friendly":
        items = [t for t in TEMPLATES if not t.presentation_oriented]
    elif filt == "Presentation":
        items = [t for t in TEMPLATES if t.presentation_oriented]
    with st.spinner("Rendering previews…"):
        cols = st.columns(3)
        for i, t in enumerate(items):
            with cols[i % 3], st.container(border=True, key=f"template_card_{t.id}"):
                st.image(thumbnail(t.id), width="stretch", caption=f"{t.name} preview (fictional sample)")
                sel = t.id == cur
                st.markdown(f"**{t.name}** " + (badge("pass", "Selected") if sel else ""), unsafe_allow_html=True)
                st.markdown(badge("presentation") if t.presentation_oriented else badge("ats"), unsafe_allow_html=True)
                st.caption(("Two columns" if t.layout == "sidebar" else "Single column") + " · " + FONTS[t.font]["label"].split(" (")[0])
                with st.expander("Details"):
                    st.caption(t.description)
                    st.markdown(f"**Best for:** {', '.join(t.recommended_for)}  \n"
                                f"**Length options:** {', '.join({'1': '1 page', '2': '2 pages', 'academic': 'academic CV'}[x] for x in t.page_options)}  \n"
                                f"**Font:** {FONTS[t.font]['label']}  \n**Parsing:** {t.parsing_notes}")
                st.button("Selected ✓" if sel else "Use this template", key=f"sel_{t.id}", on_click=_select, args=(t.id,),
                          disabled=sel, width="stretch", type="primary" if not sel else "secondary")
    spec = get_template(cur)
    if spec.presentation_oriented:
        st.warning(f"**{spec.name}** is presentation-oriented. A separate single-column, parsing-friendly PDF and DOCX "
                   "will also be generated for online application portals.")
    _customise()
    nav_buttons()
