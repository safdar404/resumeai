"""Intake: extract candidate details from chat messages or resume documents."""
from __future__ import annotations

import re

from src.models.profile import CandidateProfile, new_id
from src.prompts.templates import DOCUMENT_INTAKE_PROMPT, INTAKE_PROMPT
from src.security.untrusted import fence
from src.services import chat_intake
from src.services.heuristic_parser import parse_resume_text
from src.services.llm import LLMError, LLMService
from src.services.text_utils import content_words, norm_key, numbers_in


def _k(*vals: str) -> str:
    return "|".join(norm_key(v) for v in vals)


def merge_profiles(base: CandidateProfile, patch: CandidateProfile) -> CandidateProfile:
    """Merge patch into base. Scalars from patch overwrite only when non-empty;
    list entries are de-duplicated by natural keys; ids are kept unique."""
    b = base.model_copy(deep=True)
    for f in ("full_name", "headline", "summary"):
        v = getattr(patch, f)
        if v:
            setattr(b, f, v)
    for f in ("email", "phone", "city", "country", "linkedin", "github", "portfolio"):
        v = getattr(patch.contact, f)
        if v:
            setattr(b.contact, f, v)
    urls = {l.url for l in b.contact.other_links}
    b.contact.other_links += [l for l in patch.contact.other_links if l.url and l.url not in urls]
    for f in ("occupation", "sector", "seniority", "location", "job_description"):
        v = getattr(patch.target, f)
        if v:
            setattr(b.target, f, v)
    if patch.career_stage != "mid":
        b.career_stage = patch.career_stage

    def merge_list(name: str, key, bullet_field: str | None = None):
        existing = getattr(b, name)
        index = {key(x): x for x in existing}
        for item in getattr(patch, name):
            k = key(item)
            if not k.strip("|"):
                continue
            if k in index:
                cur = index[k]
                for fld, val in item.model_dump().items():
                    if fld in ("id", bullet_field):
                        continue
                    if val and not getattr(cur, fld):
                        setattr(cur, fld, val)
                if bullet_field:
                    have = {norm_key(x) for x in getattr(cur, bullet_field)}
                    getattr(cur, bullet_field).extend(x for x in getattr(item, bullet_field) if norm_key(x) not in have)
            else:
                item = item.model_copy(deep=True)
                if hasattr(item, "id"):
                    item.id = new_id()
                existing.append(item)
                index[k] = item

    merge_list("experience", lambda e: _k(e.title, e.employer), "bullets")
    merge_list("education", lambda e: _k(e.degree, e.institution), "details")
    merge_list("certifications", lambda c: _k(c.name))
    merge_list("projects", lambda p: _k(p.name), "bullets")
    merge_list("publications", lambda p: _k(p.title))
    merge_list("languages", lambda l: _k(l.language))
    merge_list("awards", lambda a: _k(a.title))
    merge_list("volunteering", lambda v: _k(v.role, v.organization), "bullets")
    merge_list("referees", lambda r: _k(r.name))
    for kind in ("technical", "interpersonal"):
        have = {s.lower() for s in getattr(b.skills, kind)}
        for s in getattr(patch.skills, kind):
            if s and s.lower() not in have:
                getattr(b.skills, kind).append(s)
                have.add(s.lower())
    return b


def profile_brief(p: CandidateProfile) -> str:
    bits = [f"name={p.full_name or '?'}", f"target={p.target.occupation or '?'}",
            f"roles={[f'{e.title} @ {e.employer}' for e in p.experience]}",
            f"education={[e.degree for e in p.education]}", f"skills={p.skills.technical[:15]}"]
    return "; ".join(bits)


def unverified_paths(extracted: CandidateProfile, source_text: str) -> list[str]:
    """Paths of extracted values that cannot be traced to the source text."""
    src_words = set(content_words(source_text))
    src_norm = norm_key(source_text)
    src_numbers = numbers_in(source_text)
    out: list[str] = []

    def check(path: str, value: str):
        if not value or len(value) < 3:
            return
        words = content_words(value)
        if numbers_in(value) - src_numbers:
            out.append(path); return
        if words:
            found = sum(1 for w in words if w in src_words)
            if found / len(words) < 0.75 and norm_key(value) not in src_norm:
                out.append(path)

    check("full_name", extracted.full_name)
    for i, e in enumerate(extracted.experience):
        check(f"experience[{i}].title", e.title); check(f"experience[{i}].employer", e.employer)
        check(f"experience[{i}].start_date", e.start_date); check(f"experience[{i}].end_date", e.end_date)
        for j, bl in enumerate(e.bullets):
            check(f"experience[{i}].bullets[{j}]", bl)
    for i, ed in enumerate(extracted.education):
        check(f"education[{i}].institution", ed.institution); check(f"education[{i}].degree", ed.degree)
    for i, c in enumerate(extracted.certifications):
        check(f"certifications[{i}].name", c.name)
    for i, s in enumerate(extracted.skills.technical):
        check(f"skills.technical[{i}]", s)
    return out


def intake_chat(profile: CandidateProfile, message: str, asked_field: str | None,
                llm: LLMService | None) -> tuple[CandidateProfile, list[str], list[str]]:
    """Returns (profile, notes, errors)."""
    errors: list[str] = []
    p = profile.model_copy(deep=True)
    if asked_field and chat_intake.is_skip(message):
        notes = chat_intake.apply_answer(p, asked_field, message)
        return p, notes, errors
    if llm is not None:
        try:
            patch = llm.structured(CandidateProfile, INTAKE_PROMPT, {
                "asked_field": asked_field or "anything", "profile_brief": profile_brief(p),
                "message": fence(message, "candidate_data")})
            patch.skipped_fields = []
            before = p.model_dump_json()
            p = merge_profiles(p, patch)
            if p.model_dump_json() != before:
                return p, ["details extracted"], errors
            # nothing extracted — fall through to rules for the asked field
        except LLMError as e:
            errors.append(f"AI extraction unavailable ({e.user_message()}) — used the offline rules instead.")
    notes = chat_intake.apply_answer(p, asked_field, message)
    return p, notes, errors


def intake_document(profile: CandidateProfile, text: str, llm: LLMService | None
                    ) -> tuple[CandidateProfile, list[str], list[str], str]:
    """Returns (merged profile, unverified paths, errors, method)."""
    errors: list[str] = []
    extracted, method = None, "rules"
    if llm is not None:
        try:
            extracted = llm.structured(CandidateProfile, DOCUMENT_INTAKE_PROMPT,
                                       {"document": fence(text, "candidate_data")})
            extracted.skipped_fields = []
            method = "llm"
        except LLMError as e:
            errors.append(f"AI import unavailable ({e.user_message()}) — used the offline parser instead.")
    if extracted is None:
        extracted = parse_resume_text(text)
    unverified = unverified_paths(extracted, text) if method == "llm" else []
    merged = merge_profiles(profile, extracted)
    # map unverified paths from extracted indices to merged indices (append offsets)
    remapped = []
    offsets = {"experience": len(profile.experience), "education": len(profile.education),
               "certifications": len(profile.certifications)}
    for path in unverified:
        m = re.match(r"(experience|education|certifications)\[(\d+)\](.*)", path)
        if m:
            remapped.append(f"{m.group(1)}[{int(m.group(2)) + offsets[m.group(1)]}]{m.group(3)}")
        else:
            remapped.append(path)
    return merged, remapped, errors, method
