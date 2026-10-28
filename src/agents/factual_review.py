"""Factual review: detect unsupported claims and altered facts in a draft."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from src.agents.drafting import contact_items, rule_summary
from src.models.paths import PathError, get_path
from src.models.profile import CandidateProfile
from src.models.resume import ResumeDocument
from src.services.dates import total_experience_years
from src.services.taxonomy import canonical, find_terms
from src.services.text_utils import numbers_in

COMMON_CAPS = set("""I A An The And Or For With In On At To Of By From As Into Over Under Led Managed Developed Built
Designed Created Delivered Improved Reduced Increased Supported Coordinated Implemented Conducted Prepared Produced
Analysed Analyzed Trained Mentored Supervised Experienced Skilled Seeking Proven Results Driven Professional
Specialist Analyst Engineer Manager Graduate Senior Junior Lead Team Teams Data Project Projects Research Strong
Expertise Background Focus Focused Committed Passionate Dedicated Detail Oriented Technical Skills Experience Years
Including Across Using Through Within Maintained Monitored Automated Integrated Deployed Tested Reviewed Assisted
Handled Oversaw Negotiated Presented Researched Evaluated Assessed Launched Established Streamlined Migrated
Optimized Optimised Audited Reconciled Administered Performed Provided Ensured Worked Helped Mapped Wrote Taught
Planned Organized Organised Collected Processed Surveyed Modelled Modeled Classified Digitised Digitized Partnered
Collaborated Facilitated Drove Spearheaded Owned Executed Generated Achieved Resolved Identified Translated
Documented Configured Engineered Architected Contributed Recognised Recognized Awarded Selected Served""".split())


class Finding(BaseModel):
    location: str
    text: str
    problems: list[str] = Field(default_factory=list)
    action: str = "flagged"   # reverted | flagged


class ReviewReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    checked_units: int = 0
    reverted: int = 0
    passed: bool = True


def _terms(text: str) -> set[str]:
    return {canonical(t) for t in find_terms(text)}


def _proper_tokens(text: str) -> set[str]:
    out = set()
    for sent in re.split(r"(?<=[.!?;:])\s+", text):
        words = re.findall(r"[A-Za-z][A-Za-z0-9&+#.'-]*", sent)
        for w in words[1:]:
            w2 = w.rstrip(".")
            if (w2[:1].isupper() or w2.isupper()) and w2 not in COMMON_CAPS:
                out.add(w2)
    return out


def check_unit(text: str, source: str, corpus: str, corpus_lower_words: set[str], years: float,
               corpus_terms: set[str]) -> list[str]:
    problems = []
    extra_nums = numbers_in(text) - numbers_in(source) - ({str(int(years))} if source == corpus else set())
    if extra_nums:
        problems.append("numbers not in your information: " + ", ".join(sorted(extra_nums)))
    m = re.search(r"(\d+)\+?\s*years", text)
    if m and int(m.group(1)) > max(int(years), 0) and m.group(1) not in numbers_in(corpus):
        problems.append(f"claims {m.group(1)} years of experience; your dates show about {years:g}")
    new_terms = _terms(text) - _terms(source) if source != corpus else _terms(text) - corpus_terms
    if new_terms:
        problems.append("skills/tools not documented here: " + ", ".join(sorted(new_terms)))
    proper = {t for t in _proper_tokens(text) if t.lower() not in corpus_lower_words
              and canonical(t) not in corpus_terms}
    if proper:
        problems.append("names/terms not in your information: " + ", ".join(sorted(proper)))
    return problems


def review(doc: ResumeDocument, p: CandidateProfile, *, revert: bool = True) -> tuple[ResumeDocument, ReviewReport]:
    """Check every drafted unit against its source. Unsupported generated units
    are reverted to the candidate's own wording; user edits are only flagged."""
    doc = doc.model_copy(deep=True)
    rep = ReviewReport()
    corpus = p.corpus()
    corpus_words = {w.lower().rstrip(".") for w in re.findall(r"[A-Za-z][A-Za-z0-9&+#.'-]*", corpus)}
    corpus_terms = _terms(corpus)
    years = total_experience_years(p.experience)
    data = p.model_dump()
    edited = set(doc.user_edited_paths)

    # identity & contact facts must match exactly
    if doc.name != p.full_name:
        rep.findings.append(Finding(location="Name", text=doc.name, problems=["name differs from profile"],
                                    action="reverted"))
        doc.name = p.full_name; rep.reverted += 1
    expected_contact = contact_items(p)
    if doc.contact_items != expected_contact:
        if "contact" in edited:
            rep.findings.append(Finding(location="Contact", text=" | ".join(doc.contact_items),
                                        problems=["contact details differ from profile"], action="flagged"))
        else:
            doc.contact_items = expected_contact
            rep.findings.append(Finding(location="Contact", text="", problems=["contact details differed"], action="reverted"))
            rep.reverted += 1

    for sec in doc.sections:
        if sec.key == "summary" and sec.text:
            rep.checked_units += 1
            probs = check_unit(sec.text, corpus, corpus, corpus_words, years, corpus_terms)
            if probs:
                is_user = "summary" in edited
                act = "flagged" if (is_user or not revert) else "reverted"
                rep.findings.append(Finding(location="Summary", text=sec.text, problems=probs, action=act))
                if act == "reverted":
                    sec.text = rule_summary(p, [], [])
                    rep.reverted += 1
        for en in sec.entries:
            src_entry = None
            if en.source_path:
                try:
                    src_entry = get_path(data, en.source_path)
                except PathError:
                    src_entry = None
            if src_entry and sec.key == "experience":
                if en.heading != src_entry.get("title") or en.subheading != src_entry.get("employer"):
                    rep.findings.append(Finding(location=f"{sec.title}: {en.heading}", text=en.heading,
                                                problems=["job title or employer differs from profile"], action="reverted"))
                    en.heading, en.subheading = src_entry.get("title", ""), src_entry.get("employer", "")
                    rep.reverted += 1
            new_bullets = []
            for b, src_path in zip(en.bullets, en.bullet_sources or [""] * len(en.bullets)):
                rep.checked_units += 1
                try:
                    source = get_path(data, src_path) if src_path else corpus
                except PathError:
                    source = corpus
                if not isinstance(source, str):
                    source = corpus
                if b == source:
                    new_bullets.append(b); continue
                entry_ctx = source + " " + (en.heading or "") + " " + (en.subheading or "")
                probs = check_unit(b, entry_ctx, corpus, corpus_words, years, corpus_terms)
                if probs:
                    is_user = src_path in edited
                    act = "flagged" if (is_user or not revert) else "reverted"
                    rep.findings.append(Finding(location=f"{sec.title}: {en.heading}", text=b, problems=probs, action=act))
                    if act == "reverted":
                        new_bullets.append(source if source is not corpus else b)
                        rep.reverted += 1
                        continue
                new_bullets.append(b)
            en.bullets = new_bullets
    rep.passed = not any(f.action == "flagged" for f in rep.findings)
    return doc, rep
