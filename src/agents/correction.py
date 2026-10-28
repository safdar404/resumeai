"""Language-correction agent plus accept / reject / undo operations."""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.corrections import Correction
from src.models.paths import PathError, get_path, set_path
from src.models.profile import CandidateProfile
from src.prompts.templates import CORRECTION_PROMPT
from src.security.untrusted import fence
from src.services.correction import facts_preserved, run_rule_corrections
from src.services.llm import LLMError, LLMService


class _LLMFix(BaseModel):
    path: str
    corrected: str
    explanation: str = ""
    factual_change: bool = False


class _LLMFixes(BaseModel):
    items: list[_LLMFix] = Field(default_factory=list)


def _apply(data: dict, c: Correction) -> bool:
    try:
        if get_path(data, c.path) != c.original:
            return False
        set_path(data, c.path, c.corrected)
        return True
    except PathError:
        return False


def run_corrections(profile: CandidateProfile, checked: dict[str, str], rejected: set[str],
                    llm: LLMService | None) -> tuple[CandidateProfile, list[Correction], dict[str, str], list[str]]:
    """Returns (profile with routine fixes applied, new corrections, updated checked map, errors)."""
    errors: list[str] = []
    data = profile.model_dump()
    rule = run_rule_corrections(profile, already_checked=checked, rejected=rejected)
    out: list[Correction] = []
    for c in rule:
        if c.status == "applied" and not c.requires_confirmation:
            if _apply(data, c):
                out.append(c)
        else:
            out.append(c)
    current = CandidateProfile.model_validate(data)

    if llm is not None:
        items = [(p, t) for p, t in current.prose_fields() if checked.get(p) != t]
        if items:
            protected = current.protected_terms()
            try:
                res = llm.structured(_LLMFixes, CORRECTION_PROMPT, {
                    "protected": ", ".join(sorted(protected))[:3000],
                    "items": fence("\n".join(f"{p}: {t}" for p, t in items[:80]), "candidate_data")})
                valid_paths = dict(items)
                for fx in res.items:
                    orig = valid_paths.get(fx.path)
                    if orig is None or not fx.corrected.strip() or fx.corrected == orig:
                        continue
                    ok, why = facts_preserved(orig, fx.corrected, protected)
                    needs = fx.factual_change or not ok
                    expl = fx.explanation or "language correction"
                    if not ok:
                        expl += f" — needs your confirmation ({why})"
                    c = Correction(path=fx.path, original=orig, corrected=fx.corrected, explanation=expl,
                                   categories=["llm"], requires_confirmation=needs,
                                   status="pending" if needs else "applied", source="llm")
                    if c.signature() in rejected:
                        continue
                    # drop rule suggestions superseded by an LLM fix of the same field
                    out = [o for o in out if not (o.path == c.path and o.status == "pending")]
                    if c.status == "applied":
                        if _apply(data, c):
                            out.append(c)
                    else:
                        out.append(c)
                current = CandidateProfile.model_validate(data)
            except LLMError as e:
                errors.append(f"AI language correction unavailable ({e.user_message()}) — offline rules were used.")
    new_checked = dict(checked)
    for p, t in current.prose_fields():
        new_checked[p] = t
    return current, out, new_checked, errors


# ------------------------------------------------------------------ user operations
def accept(profile: CandidateProfile, c: Correction) -> tuple[CandidateProfile, bool, str]:
    data = profile.model_dump()
    if _apply(data, c):
        return CandidateProfile.model_validate(data), True, "Applied."
    return profile, False, "The text has changed since this suggestion was made, so it was not applied."


def revert(profile: CandidateProfile, c: Correction) -> tuple[CandidateProfile, bool, str]:
    data = profile.model_dump()
    try:
        if get_path(data, c.path) != c.corrected:
            return profile, False, "The text was edited after the correction, so it was left unchanged."
        set_path(data, c.path, c.original)
    except PathError:
        return profile, False, "That field no longer exists."
    return CandidateProfile.model_validate(data), True, "Restored the original wording."
