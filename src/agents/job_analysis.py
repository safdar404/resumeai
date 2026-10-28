"""Job analysis: extract requirements from a job description."""
from __future__ import annotations

import re

from src.models.job import JobAnalysis, JobRequirement
from src.prompts.templates import JOB_ANALYSIS_PROMPT
from src.security.untrusted import fence
from src.services.llm import LLMError, LLMService
from src.services.taxonomy import SECTORS, canonical, detect_sector, find_terms
from src.services.text_utils import content_words, normalize_ws

PREFERRED_RE = re.compile(r"\b(preferred|nice to have|desirable|advantage|advantageous|a plus|bonus|ideally|beneficial)\b", re.I)
REQ_HINT_RE = re.compile(r"\b(experience|proficien|knowledge|familiar|ability|skills?|degree|bachelor|master|phd|"
                         r"certif|licen[cs]e|must|required|requirement|expert|understanding|qualified|qualification|"
                         r"years|competen|demonstrated|track record|strong)\b", re.I)
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years?", re.I)
SENIORITY = [("intern", "Intern"), ("graduate", "Graduate"), ("junior", "Junior"), ("entry", "Entry level"),
             ("senior", "Senior"), ("lead", "Lead"), ("principal", "Principal"), ("head of", "Head"),
             ("director", "Director"), ("manager", "Manager")]
EDU_RE = re.compile(r"\b(degree|bachelor|master|phd|bsc|msc|ba|ma|diploma|qualification)\b", re.I)
CERT_RE = re.compile(r"\b(certif|licen[cs]e|chartered|registered)\w*", re.I)


BULLET_LINE = re.compile(r"^\s*(?:[•▪◦●\-–*·]|\d+[.)])\s+")
DESCRIPTIVE = re.compile(r"\b(we are|we're|is looking for|are looking for|you will join|join our|about us|our team|"
                         r"we offer|benefits|salary|apply|equal opportunit)", re.I)
STRONG_REQ = re.compile(r"\b(must|required|essential|minimum|at least|\d+\+?\s*years)\b", re.I)


PREF_HEADER = re.compile(r"^\W*(preferred|nice to have|desirable|bonus|advantageous|a plus|good to have)\b", re.I)
REQ_HEADER = re.compile(r"^\W*(requirements|required|essential|must have|qualifications|what you.ll need|"
                        r"what we.re looking for|skills|experience|about you|responsibilities)\b", re.I)


def _candidate_lines(jd: str) -> list[tuple[str, bool]]:
    """Requirement candidates. When the posting uses bullet lists, only bullet
    lines (plus sentences with explicit requirement language) are used."""
    raw_lines = jd.splitlines()
    has_bullets = sum(1 for l in raw_lines if BULLET_LINE.match(l)) >= 3
    out: list[tuple[str, bool]] = []
    pref_block = False
    for line in raw_lines:
        is_bullet = bool(BULLET_LINE.match(line))
        stripped = line.strip()
        if not is_bullet and len(stripped) <= 60:
            if PREF_HEADER.match(stripped):
                pref_block = True
            elif REQ_HEADER.match(stripped):
                pref_block = False
        pieces = [line] if is_bullet else re.split(r"(?<=[.;])\s+(?=[A-Z])", line)
        for piece in pieces:
            s = normalize_ws(BULLET_LINE.sub("", piece))
            if not (12 <= len(s) <= 400):
                continue
            if has_bullets and not is_bullet and not STRONG_REQ.search(s):
                continue
            if DESCRIPTIVE.search(s) and not STRONG_REQ.search(s):
                continue
            out.append((s, pref_block))
    return out


def analyse_rules(jd: str, occupation: str = "") -> JobAnalysis:
    lines = _candidate_lines(jd)
    title = occupation
    m = re.search(r"(?:job title|position|role)\s*[:\-]\s*(.+)", jd, re.I)
    if m:
        title = normalize_ws(m.group(1))[:80]
    elif not title and lines:
        first = lines[0]
        if len(first) <= 70:
            title = first
    low = jd.lower()
    seniority = next((lbl for k, lbl in SENIORITY if k in (title or "").lower()), "") or \
        next((lbl for k, lbl in SENIORITY if re.search(r"\b" + k + r"\b", low)), "")
    reqs: list[JobRequirement] = []
    seen_kw: set[tuple] = set()
    for s, in_pref_block in lines:
        if re.match(r"^(job title|position|role|title|about (the|us)|location|salary|company)\s*[:\-]?", s, re.I) and len(s) < 120:
            continue
        if PREF_HEADER.match(s) and len(s) < 40:
            continue
        kws = find_terms(s)
        yrs = YEARS_RE.search(s)
        if not kws and not REQ_HINT_RE.search(s):
            continue
        if not kws and not yrs and not EDU_RE.search(s) and not CERT_RE.search(s):
            # generic requirement — keep only if it reads like one
            if not re.search(r"\b(must|required|ability to|experience (in|with))\b", s, re.I):
                continue
        key = (normalize_ws(s).lower(),)
        if key in seen_kw:
            continue
        seen_kw.add(key)
        cat = "skill"
        if yrs and re.search(r"experience", s, re.I):
            cat = "experience"
        elif re.search(r"\b(degree|bachelor|master|phd|doctorate|bsc|msc)\b", s, re.I) or (EDU_RE.search(s) and not kws):
            cat = "education"
        elif CERT_RE.search(s):
            cat = "certification"
        importance = "preferred" if (PREFERRED_RE.search(s) or in_pref_block) else "required"
        reqs.append(JobRequirement(id=f"r{len(reqs) + 1}", text=s[:240], keywords=kws or content_words(s)[:4],
                                   importance=importance, category=cat,
                                   years=int(yrs.group(1)) if yrs and cat == "experience" else None))
        if len(reqs) >= 20:
            break
    all_kw = []
    for r in reqs:
        for k in r.keywords:
            if k not in all_kw:
                all_kw.append(k)
    return JobAnalysis(title=title, sector=detect_sector(jd + " " + occupation), seniority=seniority,
                       requirements=reqs, keywords=all_kw, method="rules")


def analyse_job(jd: str, occupation: str, llm: LLMService | None) -> tuple[JobAnalysis, list[str]]:
    errors: list[str] = []
    if not jd.strip():
        return JobAnalysis(title=occupation, sector=detect_sector(occupation), method="rules"), errors
    rules = analyse_rules(jd, occupation)
    if llm is None:
        return rules, errors
    try:
        res = llm.structured(JobAnalysis, JOB_ANALYSIS_PROMPT, {
            "sectors": ", ".join(list(SECTORS) + ["general"]), "job_description": fence(jd, "job_description")})
        reqs = []
        for i, r in enumerate(res.requirements[:20]):
            r.id = f"r{i + 1}"
            r.keywords = [canonical(k) for k in r.keywords if k.strip()][:6] or content_words(r.text)[:4]
            if r.category == "experience" and r.years is None:
                m = YEARS_RE.search(r.text)
                r.years = int(m.group(1)) if m else None
            reqs.append(r)
        if not reqs:
            errors.append("The AI provider returned no requirements for this job description — rule-based analysis was used.")
            return rules, errors
        res.requirements = reqs
        res.sector = res.sector if res.sector in SECTORS else rules.sector
        res.keywords = sorted({k for r in reqs for k in r.keywords})
        res.method = "llm"
        return res, errors
    except LLMError as e:
        errors.append(f"AI job analysis unavailable ({e.user_message()}) — used rule-based analysis.")
        return rules, errors
