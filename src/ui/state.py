"""Session state for one browser session. Nothing here is shared between
visitors: Streamlit's session_state is per session, and each session owns its
own WorkflowRunner (graph + in-memory checkpointer + random thread id).
Candidate documents are processed in memory and never written to disk."""
from __future__ import annotations

import gc
import uuid
from typing import Any

import streamlit as st

from src.config import PROVIDERS, get_secret, provider_defaults
from src.graph.runner import WorkflowRunner
from src.models.corrections import Correction
from src.models.profile import CandidateProfile
from src.services.llm import LLMService, LLMSettings, build_service
from src.templates.registry import DEFAULT_TEMPLATE, RenderOptions

STEPS = ["Start", "Add information", "Review corrections", "Target job", "Choose template", "Generate", "Edit",
         "Validate", "Download"]


def init() -> None:
    ss = st.session_state
    if "session_id" in ss:
        return
    d = provider_defaults()
    ss.session_id = uuid.uuid4().hex
    ss.runner = WorkflowRunner()
    ss.step = 0
    ss.profile = CandidateProfile()
    ss.profile_version = 0
    ss.chat = []
    ss.asked_counts = {}
    ss.next_field = None
    ss.corrections = []
    ss.checked_fields = {}
    ss.rejected = []
    ss.undo_stack = []
    ss.validation = None
    ss.unverified = []
    ss.template_id = DEFAULT_TEMPLATE
    ss.options = RenderOptions().model_dump()
    ss.results = None
    ss.interrupt = None
    ss.notices = []
    ss.llm = {"provider": d.provider, "model": d.model, "base_url": d.base_url, "session_key": "", "consent": False,
              "verified": None}


def reset_session() -> None:
    """Clear my session and files: drop every key, the runner and its checkpoints."""
    runner = st.session_state.get("runner")
    if runner is not None:
        runner.reset()
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    gc.collect()
    init()


def profile() -> CandidateProfile:
    return st.session_state.profile


def set_profile(p: CandidateProfile, *, external: bool = True) -> None:
    """Replace the profile. ``external`` bumps the version so form widgets
    re-initialise from the new values (keeps chat and forms in sync)."""
    st.session_state.profile = p
    if external:
        st.session_state.profile_version += 1
    st.session_state.results_stale = True


def goto(step: int) -> None:
    st.session_state.step = max(0, min(step, len(STEPS) - 1))
    st.session_state["nav_radio"] = STEPS[st.session_state.step]


# ------------------------------------------------------------------ LLM
def resolve_key() -> tuple[str | None, str]:
    cfg = st.session_state.llm
    if cfg.get("session_key"):
        return cfg["session_key"], "entered in this session"
    secret_name = PROVIDERS.get(cfg["provider"], {}).get("secret")
    v = get_secret(secret_name) if secret_name else None
    return v, ("app secrets / environment" if v else "not configured")


def llm_service() -> LLMService | None:
    """Return the configured service, or None for offline mode. Errors are
    surfaced to the user, never hidden."""
    cfg = st.session_state.llm
    if cfg["provider"] == "none":
        return None
    if not cfg.get("consent"):
        note("AI provider selected but data-sharing consent not given — the offline engine was used.", "warning")
        return None
    key, _ = resolve_key()
    svc, err = build_service(LLMSettings(provider=cfg["provider"], model=cfg["model"], api_key=key,
                                         base_url=cfg.get("base_url", "")))
    if err:
        note(f"AI provider unavailable: {err} The offline engine was used instead.", "error")
    return svc


def note(msg: str, level: str = "info") -> None:
    if (level, msg) not in st.session_state.notices:
        st.session_state.notices.append((level, msg))


def show_notices() -> None:
    for level, msg in st.session_state.get("notices", []):
        getattr(st, level if level in ("info", "warning", "error", "success") else "info")(msg)
    st.session_state.notices = []


# ------------------------------------------------------------------ workflow bridge
def _absorb(res: dict[str, Any]) -> None:
    ss = st.session_state
    if "profile" in res:
        new = CandidateProfile.model_validate(res["profile"])
        if new.model_dump() != ss.profile.model_dump():
            set_profile(new)
    for key in ("validation", "checked_fields", "asked_counts", "unverified"):
        if res.get(key) is not None:
            setattr(ss, key, res[key])
    if res.get("corrections") is not None:
        ss.corrections = res["corrections"]
    if "next_field" in res:
        ss.next_field = res["next_field"]
    for e in res.get("errors") or []:
        note(e, "warning")


def run_intake(kind: str, raw: str = "") -> dict:
    ss = st.session_state
    res = ss.runner.run({"mode": "intake", "input_kind": kind, "raw_input": raw, "asked_field": ss.next_field,
                         "asked_counts": ss.asked_counts, "profile": ss.profile.model_dump(),
                         "corrections": ss.corrections, "checked_fields": ss.checked_fields,
                         "rejected": ss.rejected, "unverified": ss.unverified if kind != "document" else []},
                        llm_service())
    if kind == "document":
        res["unverified"] = sorted(set(ss.unverified) | set(res.get("unverified") or []))
    _absorb(res)
    return res


def refresh_checks() -> None:
    """Validate and language-check after form edits or imports."""
    run_intake("profile")


def run_generate() -> dict:
    ss = st.session_state
    res = ss.runner.run({"mode": "generate", "profile": ss.profile.model_dump(), "template_id": ss.template_id,
                         "options": ss.options, "corrections": ss.corrections, "unverified": ss.unverified,
                         "clarification_rounds": 0}, llm_service())
    return _after_generate(res)


def resume_generate(answers: dict) -> dict:
    return _after_generate(st.session_state.runner.resume(answers, llm_service()))


def _after_generate(res: dict) -> dict:
    ss = st.session_state
    _absorb(res)
    ss.interrupt = res.get("interrupt")
    if res.get("pdf"):
        ss.results = res
        ss.results_stale = False
    return res


def run_rerender(draft: dict) -> dict:
    ss = st.session_state
    base = ss.results or {}
    res = ss.runner.run({"mode": "rerender", "profile": ss.profile.model_dump(), "template_id": ss.template_id,
                         "options": ss.options, "draft": draft, "job_analysis": base.get("job_analysis"),
                         "matches": base.get("matches") or [], "validation": ss.validation,
                         "corrections": ss.corrections}, llm_service())
    if res.get("pdf"):
        merged = dict(base)
        merged.update(res)
        ss.results = merged
        ss.results_stale = False
    for e in res.get("errors") or []:
        note(e, "warning")
    return res


def corrections() -> list[Correction]:
    return [Correction.model_validate(c) for c in st.session_state.corrections]


def save_corrections(items: list[Correction]) -> None:
    st.session_state.corrections = [c.model_dump() for c in items]
