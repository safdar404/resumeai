"""Small, accessible UI building blocks."""
from __future__ import annotations

import difflib
import html

import streamlit as st

from src.ui.theme import RAINBOW

STATUS_STYLE = {
    "complete": ("#06D6A0", "✓ Complete"), "partial": ("#FF9F1C", "◐ Partial"), "missing": ("#FF4D6D", "○ Missing"),
    "skipped": ("#9B5DE5", "↷ Skipped"), "supported": ("#06D6A0", "✓ Supported"),
    "transferable": ("#22B8F0", "↔ Transferable"), "not_demonstrated": ("#FF4D6D", "✗ Not demonstrated"),
    "needs_clarification": ("#FF9F1C", "? Needs clarification"), "pass": ("#06D6A0", "✓ Pass"),
    "fail": ("#FF4D6D", "✗ Fail"), "warn": ("#FF9F1C", "! Check"), "info": ("#22B8F0", "i Info"),
    "applied": ("#06D6A0", "✓ Applied"), "pending": ("#FF9F1C", "? Awaiting you"), "rejected": ("#9B5DE5", "↶ Rejected"),
    "accepted": ("#06D6A0", "✓ Accepted"), "estimate": ("#22B8F0", "≈ Estimate"), "rules": ("#9B5DE5", "⚙ Rule-based"),
    "presentation": ("#FF9F1C", "◧ Presentation-oriented"), "ats": ("#06D6A0", "▤ Parsing-friendly"),
}


def badge(kind: str, label: str | None = None) -> str:
    color, default = STATUS_STYLE.get(kind, ("#22B8F0", kind))
    return f'<span class="cr-badge" style="--b:{color}"><span class="dot"></span>{html.escape(label or default)}</span>'


def badges(*items: tuple[str, str | None]) -> None:
    st.markdown("".join(badge(k, l) for k, l in items), unsafe_allow_html=True)


def step_header(index: int, title: str, lead: str = "") -> None:
    color = RAINBOW[index % len(RAINBOW)]
    st.markdown(f'<div class="cr-step" style="--cr-c:{color}"><span class="num">Step {index + 1}</span>'
                f'<h2>{html.escape(title)}</h2></div>', unsafe_allow_html=True)
    if lead:
        st.markdown(f'<p class="cr-lead">{lead}</p>', unsafe_allow_html=True)


def progress_bar(pct: int, label: str = "") -> None:
    st.markdown(f'<div class="cr-muted">{html.escape(label)} <b>{pct}%</b></div>'
                f'<div class="cr-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">'
                f'<div style="width:{pct}%"></div></div>', unsafe_allow_html=True)


def score_ring(total: float, max_points: int, caption: str) -> None:
    pct = int(round(100 * total / max_points)) if max_points else 0
    ring = "#06D6A0" if pct >= 80 else "#FFD166" if pct >= 60 else "#FF4D6D"
    st.markdown(f'<div class="cr-score"><div class="cr-ring" style="--p:{pct};--ring:{ring}" role="img" '
                f'aria-label="{total:g} of {max_points} points"><span>{total:g}</span></div>'
                f'<div><div style="font-weight:700">{total:g} / {max_points} points ({pct}%)</div>'
                f'<div class="cr-muted">{html.escape(caption)}</div></div></div>', unsafe_allow_html=True)


def diff_html(a: str, b: str) -> str:
    sm = difflib.SequenceMatcher(None, a.split(), b.split())
    out = []
    aw, bw = a.split(), b.split()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(html.escape(" ".join(aw[i1:i2])))
        else:
            if i2 > i1:
                out.append(f"<del>{html.escape(' '.join(aw[i1:i2]))}</del>")
            if j2 > j1:
                out.append(f"<ins>{html.escape(' '.join(bw[j1:j2]))}</ins>")
    return f'<div class="cr-diff">{" ".join(out)}</div>'


def card(title: str, body_html: str = "", accent: str | None = None) -> None:
    style = f' style="--cr-c:{accent}"' if accent else ""
    cls = "cr-card cr-accent-top" if accent else "cr-card"
    st.markdown(f'<div class="{cls}"{style}><h4>{html.escape(title)}</h4>{body_html}</div>', unsafe_allow_html=True)


def empty_state(message: str, icon: str = "🌈") -> None:
    st.info(f"{icon}  {message}")
