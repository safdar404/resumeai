"""Helpers for passing untrusted text (resumes, job descriptions, chat) to an
LLM as *data*. The original text is never modified; only the prompt copy is
fenced and has look-alike fence tags neutralised."""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"</?\s*(untrusted_data|system|instructions?)\s*>", re.IGNORECASE)


def fence(text: str, label: str = "untrusted_data", limit: int = 20_000) -> str:
    safe = _FENCE_RE.sub(lambda m: m.group(0).replace("<", "‹").replace(">", "›"), text or "")
    if len(safe) > limit:
        safe = safe[:limit] + "\n[...truncated...]"
    return f"<{label}>\n{safe}\n</{label}>"


INJECTION_HINTS = re.compile(
    r"(ignore (all|any|the) (previous|prior|above) instructions|you are now|system prompt|"
    r"disregard (the|all) (rules|instructions)|give (me|this candidate) (a )?(100|perfect) score)",
    re.IGNORECASE,
)


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION_HINTS.search(text or ""))
