"""Rainbow brand layer. Colours adapt to Streamlit's native light/dark theme
(Settings → Theme) by using translucent tints and inherited text colour, so
meaning never depends on colour alone (every badge also has a text label)."""
from __future__ import annotations

import streamlit as st

RAINBOW = ["#FF4D6D", "#FF9F1C", "#FFD166", "#06D6A0", "#22B8F0", "#9B5DE5"]
GRADIENT = "linear-gradient(90deg,#FF4D6D,#FF9F1C,#FFD166,#06D6A0,#22B8F0,#9B5DE5)"

CSS = f"""
<style>
:root {{ --cr-grad: {GRADIENT}; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1240px; }}
/* brand bar */
.cr-brand {{ display:flex; align-items:center; gap:.85rem; margin:0 0 .6rem 0; }}
.cr-logo {{ width:38px; height:38px; border-radius:11px; background:var(--cr-grad); background-size:200% 100%;
           display:grid; place-items:center; color:#fff; font-weight:800; font-size:1.05rem;
           box-shadow: inset 0 0 0 2px rgba(255,255,255,.25); animation: cr-shift 9s ease-in-out infinite alternate; }}
.cr-brand h1 {{ font-size:1.32rem; line-height:1.15; margin:0; padding:0; font-weight:750; letter-spacing:-.01em; }}
.cr-brand p {{ margin:0; font-size:.86rem; opacity:.72; }}
.cr-stripe {{ height:4px; border-radius:4px; background:var(--cr-grad); margin:.2rem 0 1.1rem 0; }}
@keyframes cr-shift {{ from {{ background-position:0% 50%; }} to {{ background-position:100% 50%; }} }}
@media (prefers-reduced-motion: reduce) {{ .cr-logo, .cr-shimmer {{ animation:none !important; }} }}
/* step header */
.cr-step {{ display:flex; align-items:baseline; gap:.6rem; margin:.1rem 0 .35rem 0; }}
.cr-step .num {{ font-weight:800; font-size:.8rem; padding:.12rem .5rem; border-radius:999px; color:#1B1530;
               background:var(--cr-c, #FFD166); }}
.cr-step h2 {{ font-size:1.25rem; margin:0; padding:0; font-weight:720; }}
.cr-lead {{ opacity:.8; margin:-.1rem 0 .9rem 0; font-size:.95rem; }}
/* badges: text + colour, never colour alone */
.cr-badge {{ display:inline-flex; align-items:center; gap:.3rem; font-size:.76rem; font-weight:650; padding:.12rem .55rem;
            border-radius:999px; border:1px solid var(--b); background:color-mix(in srgb, var(--b) 16%, transparent);
            margin:0 .25rem .25rem 0; white-space:nowrap; }}
.cr-badge .dot {{ width:.5rem; height:.5rem; border-radius:50%; background:var(--b); }}
/* cards */
.cr-card {{ border:1px solid rgba(128,128,160,.28); border-radius:.8rem; padding:.8rem .95rem; margin-bottom:.6rem;
           background: rgba(128,128,160,.05); }}
.cr-card h4 {{ margin:0 0 .25rem 0; font-size:.98rem; }}
.cr-card p {{ margin:.15rem 0; font-size:.86rem; opacity:.85; }}
.cr-accent-top {{ border-top:3px solid var(--cr-c,#22B8F0); }}
/* score */
.cr-score {{ display:flex; align-items:center; gap:1rem; }}
.cr-ring {{ --p:0; position:relative; width:92px; height:92px; flex:none; display:grid; place-items:center; }}
.cr-ring::before {{ content:""; position:absolute; inset:0; border-radius:50%;
           background: conic-gradient(var(--ring,#06D6A0) calc(var(--p)*1%), rgba(128,128,160,.22) 0);
           -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 11px), #000 calc(100% - 10px));
                   mask: radial-gradient(farthest-side, transparent calc(100% - 11px), #000 calc(100% - 10px)); }}
.cr-ring span {{ position:relative; font-weight:800; font-size:1.15rem; }}
.cr-bar {{ height:8px; border-radius:6px; background:rgba(128,128,160,.22); overflow:hidden; }}
.cr-bar > div {{ height:100%; border-radius:6px; background:var(--cr-grad); }}
.cr-muted {{ opacity:.72; font-size:.85rem; }}
.cr-diff del {{ background:rgba(255,77,109,.18); text-decoration:line-through; border-radius:3px; padding:0 2px; }}
.cr-diff ins {{ background:rgba(6,214,160,.22); text-decoration:none; border-radius:3px; padding:0 2px; }}
/* keyboard focus always visible */
a:focus-visible, button:focus-visible, [role="tab"]:focus-visible, [role="radio"]:focus-visible,
input:focus-visible, textarea:focus-visible, [tabindex]:focus-visible {{
  outline: 3px solid #22B8F0 !important; outline-offset: 2px !important; }}
section[data-testid="stSidebar"] .stRadio label p {{ font-size:.92rem; }}
div[data-testid="stChatMessage"] {{ padding:.55rem .75rem; }}
img {{ border-radius:.4rem; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
