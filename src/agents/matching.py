"""Evidence matching: connect job requirements to documented experience."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from src.models.job import Evidence, JobAnalysis, RequirementMatch
from src.models.profile import CandidateProfile
from src.prompts.templates import MATCHING_PROMPT
from src.security.untrusted import fence
from src.services.dates import total_experience_years
from src.services.llm import LLMError, LLMService
from src.services.taxonomy import canonical, family_members, find_terms, term_pattern, variants
from src.services.text_utils import content_words

RANK = {"not_demonstrated": 0, "needs_clarification": 1, "transferable": 2, "supported": 3}
STRENGTH = {"supported": 1.0, "transferable": 0.5, "needs_clarification": 0.25, "not_demonstrated": 0.0}


def build_evidence(p: CandidateProfile) -> list[Evidence]:
    ev: list[Evidence] = []
    for i, e in enumerate(p.experience):
        role = f"{e.title} — {e.employer}".strip(" —")
        ev.append(Evidence(id=f"exp{i}", text=f"{e.title} at {e.employer}", source=role))
        for j, b in enumerate(e.bullets):
            ev.append(Evidence(id=f"exp{i}.b{j}", text=b, source=f"{role} (point {j + 1})"))
    for i, pr in enumerate(p.projects):
        txt = " ".join([pr.name, pr.description, " ".join(pr.bullets), ", ".join(pr.technologies)])
        ev.append(Evidence(id=f"proj{i}", text=txt, source=f"Project: {pr.name}"))
    for i, ed in enumerate(p.education):
        txt = " ".join([ed.degree, ed.field_of_study, ed.institution, " ".join(ed.details)])
        ev.append(Evidence(id=f"edu{i}", text=txt, source=f"Education: {ed.degree}"))
    for i, c in enumerate(p.certifications):
        ev.append(Evidence(id=f"cert{i}", text=f"{c.name} {c.issuer}", source=f"Certification: {c.name}"))
    for i, v in enumerate(p.volunteering):
        ev.append(Evidence(id=f"vol{i}", text=f"{v.role} {v.organization} " + " ".join(v.bullets),
                           source=f"Volunteering: {v.role}"))
    for i, pub in enumerate(p.publications):
        ev.append(Evidence(id=f"pub{i}", text=f"{pub.title} {pub.venue}", source=f"Publication: {pub.title[:40]}"))
    for i, s in enumerate(p.skills.technical):
        ev.append(Evidence(id=f"skill{i}", text=s, source="Skills list"))
    for i, s in enumerate(p.skills.interpersonal):
        ev.append(Evidence(id=f"soft{i}", text=s, source="Skills list"))
    for i, l in enumerate(p.languages):
        ev.append(Evidence(id=f"lang{i}", text=f"{l.language} {l.proficiency}", source="Languages"))
    return ev


def _mentions(text: str, term: str) -> bool:
    return any(term_pattern(v).search(text) for v in variants(term))


def _is_skill_list(e: Evidence) -> bool:
    return e.id.startswith(("skill", "soft", "lang"))


def match_rules(analysis: JobAnalysis, p: CandidateProfile) -> list[RequirementMatch]:
    ev = build_evidence(p)
    years = total_experience_years(p.experience)
    out: list[RequirementMatch] = []
    for r in analysis.requirements:
        base = dict(requirement_id=r.id, requirement=r.text, importance=r.importance)
        if r.category == "experience" and r.years:
            if years >= r.years:
                st, note = "supported", f"Your dated roles add up to about {years:g} years."
            elif years >= r.years - 1:
                st, note = "needs_clarification", (f"Your dated roles add up to about {years:g} years; the job asks for "
                                                   f"{r.years}. Add any missing roles or dates if you have them.")
            else:
                st, note = "not_demonstrated", f"Your dated roles add up to about {years:g} years (job asks for {r.years})."
            roles = [e for e in ev if e.id.startswith("exp") and "." not in e.id][:3]
            out.append(RequirementMatch(**base, status=st, strength=STRENGTH[st],
                                        evidence=roles if st != "not_demonstrated" else [], note=note))
            continue
        if r.category == "education":
            edu = [e for e in ev if e.id.startswith("edu")]
            if not edu:
                out.append(RequirementMatch(**base, status="not_demonstrated", note="No qualification listed."))
                continue
            req_words = set(content_words(r.text)) - {"degree", "bachelor", "bachelor's", "master", "master's",
                                                       "related", "field", "equivalent", "relevant"}
            best = max(edu, key=lambda e: len(req_words & set(content_words(e.text))))
            overlap = req_words & set(content_words(best.text))
            if overlap or any(_mentions(best.text, k) for k in r.keywords if find_terms(k)):
                out.append(RequirementMatch(**base, status="supported", strength=1.0, evidence=[best],
                                            note=f"Field match: {', '.join(sorted(overlap))}" if overlap else ""))
            else:
                out.append(RequirementMatch(**base, status="needs_clarification", strength=0.25, evidence=[best],
                                            note="Confirm whether your qualification counts as a related field."))
            continue
        tax_kws = [canonical(k) for k in r.keywords if find_terms(k)]
        if tax_kws:
            direct: dict[str, list[Evidence]] = {}
            related: dict[str, list[tuple[str, Evidence]]] = {}
            for k in tax_kws:
                hits = [e for e in ev if _mentions(e.text, k)]
                if hits:
                    direct[k] = hits
                else:
                    fam = family_members(k)
                    rel = [(m, e) for m in fam for e in ev if _mentions(e.text, m)]
                    if rel:
                        related[k] = rel
            alternatives = bool(re.search(r"\bor\b|such as|e\.g\.|\blike\b|/|any of", r.text, re.I))
            if alternatives and direct:
                coverage = 1.0
                missing = []
            else:
                # keywords from the same family count as one requirement group
                groups: list[set[str]] = []
                for k in tax_kws:
                    fam = family_members(k) | {k}
                    g = next((g for g in groups if g & fam), None)
                    if g is None:
                        groups.append({k})
                    else:
                        g.add(k)
                hit_groups = sum(1 for g in groups if g & set(direct))
                coverage = hit_groups / len(groups)
                missing = [k for k in tax_kws if k not in direct]
            evidence = []
            for hits in direct.values():
                for e in sorted(hits, key=_is_skill_list):
                    if e not in evidence:
                        evidence.append(e)
            if direct and (coverage >= 0.5 or len(direct) >= 2):
                contextual = any(not _is_skill_list(e) for e in evidence)
                st = "supported"
                strength = 1.0 if contextual else 0.75
                note = "" if contextual else "Only listed in your skills — add a bullet showing where you used it."
                if missing:
                    note = (note + " " if note else "") + "Not shown: " + ", ".join(missing) + "."
            elif direct or related:
                st, strength = "transferable", 0.5
                rel_terms = sorted({m for v in related.values() for m, _ in v})
                if rel_terms:
                    evidence += [e for v in related.values() for _, e in v if e not in evidence]
                note = ("Related experience: " + ", ".join(rel_terms) + ". " if rel_terms else "") + \
                       ("Not shown: " + ", ".join(missing) + "." if missing else "")
            else:
                st, strength, note = "not_demonstrated", 0.0, "No documented evidence for: " + ", ".join(missing) + "."
            out.append(RequirementMatch(**base, status=st, strength=strength, evidence=evidence[:4],
                                        missing_keywords=missing, note=note.strip()))
            continue
        # Non-taxonomy requirement: compare content words conservatively.
        req_words = set(content_words(r.text))
        best, best_ratio = None, 0.0
        for e in ev:
            ew = set(content_words(e.text))
            if not req_words or not ew:
                continue
            ratio = len(req_words & ew) / len(req_words)
            if ratio > best_ratio:
                best, best_ratio = e, ratio
        if r.category == "education" and p.education:
            st = "supported" if best and best.id.startswith("edu") and best_ratio >= 0.25 else "needs_clarification"
            note = "" if st == "supported" else "Confirm your qualification matches the field the job asks for."
            out.append(RequirementMatch(**base, status=st, strength=STRENGTH[st],
                                        evidence=[best] if best and best.id.startswith("edu") else [], note=note))
        elif best and best_ratio >= 0.6 and not _is_skill_list(best):
            out.append(RequirementMatch(**base, status="supported", strength=0.75, evidence=[best],
                                        note="Matched by wording — check the example reflects this requirement."))
        elif best and best_ratio >= 0.4:
            out.append(RequirementMatch(**base, status="needs_clarification", strength=0.25, evidence=[best],
                                        note="Possibly related — confirm or add a specific example."))
        else:
            out.append(RequirementMatch(**base, status="not_demonstrated", strength=0.0,
                                        note="No clearly related evidence found."))
    return out


class _LLMMatch(BaseModel):
    requirement_id: str
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""


class _LLMMatches(BaseModel):
    matches: list[_LLMMatch] = Field(default_factory=list)


def match_evidence(analysis: JobAnalysis, p: CandidateProfile, llm: LLMService | None
                   ) -> tuple[list[RequirementMatch], list[str]]:
    errors: list[str] = []
    rules = match_rules(analysis, p)
    if llm is None or not analysis.requirements:
        return rules, errors
    ev = {e.id: e for e in build_evidence(p)}
    try:
        res = llm.structured(_LLMMatches, MATCHING_PROMPT, {
            "requirements": fence("\n".join(f"{r.id}: {r.text}" for r in analysis.requirements), "job_description"),
            "evidence": fence("\n".join(f"{e.id}: {e.text}" for e in ev.values()), "candidate_data")})
    except LLMError as e:
        errors.append(f"AI evidence matching unavailable ({e.user_message()}) — rule-based matching was used.")
        return rules, errors
    by_id = {m.requirement_id: m for m in res.matches}
    final = []
    for rm in rules:
        lm = by_id.get(rm.requirement_id)
        if not lm or lm.status not in RANK:
            final.append(rm)
            continue
        valid = [ev[i] for i in lm.evidence_ids if i in ev]
        if lm.status in ("supported", "transferable") and not valid:
            status = min(rm.status, "needs_clarification", key=RANK.get)  # unsupported claim → downgrade
        elif valid:
            status = lm.status
        else:
            status = min(rm.status, lm.status, key=RANK.get)
        if status == "supported" and valid and all(_is_skill_list(e) for e in valid):
            strength = 0.75
        else:
            strength = STRENGTH[status]
        final.append(rm.model_copy(update={
            "status": status, "strength": strength, "evidence": (valid or rm.evidence)[:4],
            "note": (lm.note or rm.note)[:300], "method": "llm-estimate"}))
    return final, errors
