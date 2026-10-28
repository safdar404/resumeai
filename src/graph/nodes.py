"""LangGraph node functions. Each node reads typed state, does one job and
returns a partial update. The LLM service (or None for offline mode) arrives
through ``config['configurable']['llm']`` so it is never checkpointed."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.agents import correction as correction_agent
from src.agents.drafting import draft_resume
from src.agents.factual_review import review
from src.agents.intake import intake_chat, intake_document
from src.agents.job_analysis import analyse_job
from src.agents.layout import fit_suggestions, plan_layout
from src.agents.matching import match_evidence
from src.agents.validation import apply_answers, validate_profile
from src.config import MAX_DRAFT_ATTEMPTS
from src.models.corrections import Correction
from src.models.job import JobAnalysis, RequirementMatch
from src.models.profile import CandidateProfile
from src.models.resume import ResumeDocument
from src.rendering.docx_renderer import render_docx
from src.rendering.export_validation import validate_docx, validate_pdf
from src.rendering.pdf_renderer import render_pdf
from src.rendering.common import DENSITY
from src.scoring.readiness import assess
from src.services import chat_intake
from src.templates.registry import RenderOptions, get_template

MAX_CLARIFICATION_ROUNDS = 5


def _llm(config: RunnableConfig):
    return (config or {}).get("configurable", {}).get("llm")


def _profile(state) -> CandidateProfile:
    return CandidateProfile.model_validate(state.get("profile") or {})


def _progress(state, msg: str) -> list:
    return list(state.get("progress") or []) + [msg]


def _errors(state, new: list[str]) -> list:
    return list(state.get("errors") or []) + list(new)


def _options(state) -> RenderOptions:
    return RenderOptions.model_validate(state.get("options") or {})


def _max_pages(opts: RenderOptions) -> int | None:
    return None if opts.page_target == "academic" else int(opts.page_target)


# ------------------------------------------------------------------ 0. start
def start(state):
    return {"progress": [], "errors": [], "cancelled": False}


# ------------------------------------------------------------------ 1. intake
def intake(state, config: RunnableConfig):
    llm = _llm(config)
    p = _profile(state)
    if state.get("input_kind") == "profile":   # form edit / JSON import: no extraction needed
        return {"intake_notes": [], "progress": _progress(state, "Received profile update")}
    if state.get("input_kind") == "document":
        p2, unverified, errs, method = intake_document(p, state.get("raw_input", ""), llm)
        notes = [f"Imported resume ({'AI-assisted' if method == 'llm' else 'rule-based'} extraction)."]
        return {"profile": p2.model_dump(), "unverified": unverified, "intake_notes": notes,
                "progress": _progress(state, "Read your document"), "errors": _errors(state, errs)}
    p2, notes, errs = intake_chat(p, state.get("raw_input", ""), state.get("asked_field"), llm)
    return {"profile": p2.model_dump(), "intake_notes": notes, "progress": _progress(state, "Captured your details"),
            "errors": _errors(state, errs)}


# ------------------------------------------------------------------ 2. validation
def profile_validation(state):
    rep = validate_profile(_profile(state), state.get("unverified") or [])
    return {"validation": rep.model_dump(), "progress": _progress(state, "Checked your profile")}


# ------------------------------------------------------------------ 3. language correction
def language_correction(state, config: RunnableConfig):
    p = _profile(state)
    rejected = set(state.get("rejected") or [])
    p2, new, checked, errs = correction_agent.run_corrections(p, state.get("checked_fields") or {}, rejected, _llm(config))
    existing = [Correction.model_validate(c) for c in state.get("corrections") or []]
    sigs = {c.signature() for c in existing}
    merged = existing + [c for c in new if c.signature() not in sigs]
    return {"profile": p2.model_dump(), "corrections": [c.model_dump() for c in merged], "checked_fields": checked,
            "progress": _progress(state, f"Language check: {len(new)} new correction(s)"), "errors": _errors(state, errs)}


def compose_reply(state):
    """Conversation turn: acknowledge what was captured, then ask the next focused question."""
    p = _profile(state)
    asked = dict(state.get("asked_counts") or {})
    key, question = chat_intake.next_question(p, asked)
    notes = [n for n in state.get("intake_notes") or [] if n]
    fixes = [c for c in state.get("corrections") or [] if c.get("status") == "applied"]
    parts = []
    if notes:
        parts.append("Saved — " + "; ".join(notes) + ".")
    new_fix = len([c for c in fixes if c["path"] in (state.get("checked_fields") or {})])
    if notes and fixes:
        parts.append(f"I've tidied spelling/formatting in {new_fix} place(s); you can review or undo them under *Review corrections*.")
    if key:
        asked[key] = asked.get(key, 0) + 1
        parts.append(question)
    else:
        parts.append("That covers the essentials. Review your profile on the right, then continue to **Review corrections** "
                     "or **Target job**. You can keep chatting to add or fix anything.")
    return {"assistant_message": "\n\n".join(parts), "next_field": key, "asked_counts": asked,
            "progress": _progress(state, "Prepared next question")}


# ------------------------------------------------------------------ 4. clarification
def clarification(state):
    rounds = int(state.get("clarification_rounds") or 0) + 1
    issues = [i for i in (state.get("validation") or {}).get("issues", []) if i.get("blocking")]
    answers = interrupt({"issues": issues, "round": rounds})
    if not isinstance(answers, dict) or answers.get("__cancel__"):
        return {"cancelled": True, "clarification_rounds": rounds,
                "progress": _progress(state, "Paused for your answers")}
    p = apply_answers(_profile(state), {k: v for k, v in answers.items() if isinstance(v, str)})
    return {"profile": p.model_dump(), "clarification_rounds": rounds,
            "progress": _progress(state, "Applied your answers")}


# ------------------------------------------------------------------ 5. job analysis
def job_analysis(state, config: RunnableConfig):
    p = _profile(state)
    ja, errs = analyse_job(p.target.job_description, p.target.occupation, _llm(config))
    msg = (f"Analysed job description: {len(ja.requirements)} requirement(s)" if p.target.job_description
           else "No job description supplied — relevance will be shown as unavailable")
    return {"job_analysis": ja.model_dump(), "progress": _progress(state, msg), "errors": _errors(state, errs)}


# ------------------------------------------------------------------ 6. evidence matching
def evidence_matching(state, config: RunnableConfig):
    p = _profile(state)
    ja = JobAnalysis.model_validate(state.get("job_analysis") or {})
    matches, errs = match_evidence(ja, p, _llm(config))
    sup = sum(1 for m in matches if m.status == "supported")
    return {"matches": [m.model_dump() for m in matches], "draft_attempts": 0, "review_feedback": [],
            "progress": _progress(state, f"Matched evidence: {sup}/{len(matches)} requirement(s) supported"),
            "errors": _errors(state, errs)}


# ------------------------------------------------------------------ 7. drafting
def resume_drafting(state, config: RunnableConfig):
    p = _profile(state)
    ja = JobAnalysis.model_validate(state.get("job_analysis") or {})
    matches = [RequirementMatch.model_validate(m) for m in state.get("matches") or []]
    tmpl = get_template(state.get("template_id"))
    doc, errs = draft_resume(p, ja, matches, tmpl, _options(state), _llm(config), state.get("review_feedback") or None)
    attempts = int(state.get("draft_attempts") or 0) + 1
    return {"draft": doc.model_dump(), "draft_attempts": attempts,
            "progress": _progress(state, f"Drafted resume content (attempt {attempts})"), "errors": _errors(state, errs)}


# ------------------------------------------------------------------ 8. factual review
def factual_review(state):
    p = _profile(state)
    doc = ResumeDocument.model_validate(state["draft"])
    doc2, rep = review(doc, p, revert=True)
    feedback = [f"{f.location}: {'; '.join(f.problems)}" for f in rep.findings if f.action == "reverted"]
    msg = (f"Factual review: {rep.checked_units} item(s) checked, {rep.reverted} unsupported change(s) reverted"
           + (f", {sum(1 for f in rep.findings if f.action == 'flagged')} flagged for you" if not rep.passed else ""))
    return {"draft": doc2.model_dump(), "review": rep.model_dump(), "review_feedback": feedback,
            "progress": _progress(state, msg)}


# ------------------------------------------------------------------ 9. readiness (provisional)
def readiness_assessment(state):
    p = _profile(state)
    opts = _options(state)
    score = assess(p, ResumeDocument.model_validate(state["draft"]), get_template(state.get("template_id")),
                   [RequirementMatch.model_validate(m) for m in state.get("matches") or []],
                   JobAnalysis.model_validate(state["job_analysis"]) if state.get("job_analysis") else None,
                   state.get("validation"), [Correction.model_validate(c) for c in state.get("corrections") or []],
                   max_pages=_max_pages(opts))
    return {"score": score.model_dump(), "progress": _progress(state, "Assessed readiness (provisional)")}


# ------------------------------------------------------------------ 10. layout planning
def layout_planning(state):
    p = _profile(state)
    opts = _options(state)
    plan = plan_layout(ResumeDocument.model_validate(state["draft"]), p, get_template(state.get("template_id")), opts)
    return {"layout": plan.model_dump(), "progress": _progress(state, "Planned page layout")}


# ------------------------------------------------------------------ 11. rendering
def document_rendering(state):
    p = _profile(state)
    opts = _options(state)
    tmpl = get_template(state.get("template_id"))
    doc = ResumeDocument.model_validate(state["draft"])
    plan = state.get("layout") or {}
    pdf, info = render_pdf(doc, tmpl, opts, start_density=int(plan.get("start_density", 0)))
    sp = DENSITY[info.density][0]
    docx = render_docx(doc, tmpl, opts, font_key=info.font, margin_mm=info.margin_mm, body_size=info.body_size,
                       density_spacing=sp)
    out = {"pdf": pdf, "docx": docx, "ats_pdf": None, "ats_docx": None}
    if tmpl.presentation_oriented:
        apdf, ainfo = render_pdf(doc, tmpl, opts, force_single=True)
        out["ats_pdf"] = apdf
        out["ats_docx"] = render_docx(doc, tmpl, opts, font_key=ainfo.font, margin_mm=ainfo.margin_mm,
                                      body_size=ainfo.body_size, density_spacing=DENSITY[ainfo.density][0],
                                      force_single=True)
    rinfo = info.as_dict()
    if info.overflow:
        rinfo["suggestions"] = fit_suggestions(doc, p, _max_pages(opts))
    out.update({"render_info": rinfo, "progress": _progress(state, f"Rendered PDF ({info.pages} page(s)) and DOCX")})
    return out


# ------------------------------------------------------------------ 12. export validation
def export_validation(state):
    p = _profile(state)
    opts = _options(state)
    tmpl = get_template(state.get("template_id"))
    doc = ResumeDocument.model_validate(state["draft"])
    info = state.get("render_info") or {}
    max_pages = _max_pages(opts)
    pdf_rep = validate_pdf(state["pdf"], doc, p, max_pages, info.get("expected_order", []))
    docx_rep = validate_docx(state["docx"], doc, p)
    report = {"pdf": pdf_rep.model_dump(), "docx": docx_rep.model_dump(), "ats_pdf": None}
    if state.get("ats_pdf"):
        report["ats_pdf"] = validate_pdf(state["ats_pdf"], doc, p, None, []).model_dump()
    score = assess(p, doc, tmpl, [RequirementMatch.model_validate(m) for m in state.get("matches") or []],
                   JobAnalysis.model_validate(state["job_analysis"]) if state.get("job_analysis") else None,
                   state.get("validation"), [Correction.model_validate(c) for c in state.get("corrections") or []],
                   render=info, export=report, max_pages=max_pages)
    ok = pdf_rep.passed and docx_rep.passed
    return {"export_report": report, "score": score.model_dump(),
            "progress": _progress(state, "Re-opened and validated both files" + ("" if ok else " — issues found"))}


# ------------------------------------------------------------------ routing
def route_start(state) -> str:
    mode = state.get("mode", "intake")
    if mode == "rerender":
        return "factual_review"
    if mode == "generate":
        return "profile_validation"
    return "intake"


def route_after_validation(state) -> str:
    if state.get("mode") == "intake":
        return "language_correction"
    blocking = [i for i in (state.get("validation") or {}).get("issues", []) if i.get("blocking")]
    if blocking:
        if int(state.get("clarification_rounds") or 0) >= MAX_CLARIFICATION_ROUNDS:
            return "end"
        return "clarification"
    return "job_analysis"


def route_after_correction(state) -> str:
    return "compose_reply" if state.get("input_kind") == "chat" else "end"


def route_after_clarification(state) -> str:
    return "end" if state.get("cancelled") else "profile_validation"


def route_after_review(state) -> str:
    rev = state.get("review") or {}
    draft = state.get("draft") or {}
    if (state.get("mode") == "generate" and rev.get("reverted") and draft.get("generated_with") == "llm"
            and int(state.get("draft_attempts") or 0) < MAX_DRAFT_ATTEMPTS):
        return "resume_drafting"
    return "readiness_assessment"
