"""Resume drafting: build a tailored ResumeDocument using only profile facts."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from src.models.job import JobAnalysis, RequirementMatch
from src.models.profile import CandidateProfile
from src.models.resume import BulletSuggestion, ResumeDocument, ResumeEntry, ResumeSection
from src.prompts.templates import DRAFTING_PROMPT
from src.security.untrusted import fence
from src.services.dates import format_date, format_range, total_experience_years
from src.services.llm import LLMError, LLMService
from src.services.taxonomy import variants, term_pattern
from src.services.text_utils import display_url
from src.templates.registry import ALL_SECTIONS, RenderOptions, TemplateSpec


def section_order(template: TemplateSpec, profile: CandidateProfile, options: RenderOptions) -> list[str]:
    if options.section_order:
        order = [s for s in options.section_order if s in ALL_SECTIONS]
        return order + [s for s in ALL_SECTIONS if s not in order]
    order = list(template.section_order)
    stage = profile.career_stage

    def move_before(a: str, b: str):
        if a in order and b in order and order.index(a) > order.index(b):
            order.remove(a)
            order.insert(order.index(b), a)

    if stage == "graduate" or (not profile.experience and profile.education):
        move_before("education", "experience")
        move_before("projects", "experience")
    elif stage == "researcher":
        move_before("education", "experience")
        move_before("publications", "projects")
    elif stage == "career_changer":
        move_before("skills", "experience")
        move_before("projects", "experience")
    return order


def _relevance(text: str, keywords: list[str]) -> int:
    return sum(1 for k in keywords if any(term_pattern(v).search(text) for v in variants(k)))


def contact_items(p: CandidateProfile) -> list[str]:
    c = p.contact
    loc = ", ".join(x for x in (c.city, c.country) if x)
    items = [c.email, c.phone, loc, display_url(c.linkedin), display_url(c.github), display_url(c.portfolio)]
    items += [display_url(l.url) for l in c.other_links]
    return [i for i in items if i]


def rule_summary(p: CandidateProfile, matches: list[RequirementMatch], keywords: list[str]) -> str:
    """Compose a factual summary from profile data only (no invented claims)."""
    if p.summary.strip():
        return p.summary.strip()
    years = total_experience_years(p.experience)
    lead = p.headline or (p.experience[0].title if p.experience else "")
    parts = []
    if lead and years >= 1:
        parts.append(f"{lead} with {int(years)}+ years of experience")
    elif lead:
        parts.append(lead)
    elif p.education:
        ed = p.education[0]
        parts.append(f"{ed.degree}{' in ' + ed.field_of_study if ed.field_of_study else ''} graduate"
                     f"{' from ' + ed.institution if ed.institution else ''}")
    skills = sorted(p.skills.technical, key=lambda s: -_relevance(s, keywords))[:5]
    s1 = parts[0] + "." if parts else ""
    s2 = ""
    if skills:
        s2 = "Skilled in " + (", ".join(skills[:-1]) + " and " + skills[-1] if len(skills) > 1 else skills[0]) + "."
    s3 = ""
    if p.target.occupation:
        s3 = f"Seeking a {p.target.occupation} role."
    return " ".join(x for x in (s1, s2, s3) if x).strip()


class _DraftBullet(BaseModel):
    id: str
    text: str


class _DraftOut(BaseModel):
    summary: str = ""
    bullets: list[_DraftBullet] = Field(default_factory=list)


def build_document(p: CandidateProfile, analysis: JobAnalysis | None, matches: list[RequirementMatch],
                   template: TemplateSpec, options: RenderOptions) -> ResumeDocument:
    keywords = analysis.keywords if analysis else []
    doc = ResumeDocument(name=p.full_name, headline=p.headline or p.target.occupation, contact_items=contact_items(p))
    date_style = options.date_format
    sections: dict[str, ResumeSection] = {}
    summary = rule_summary(p, matches, keywords)
    sections["summary"] = ResumeSection(key="summary", title=template.title_for("summary"), kind="text", text=summary)

    tech = list(p.skills.technical)
    if keywords and options.tailor_bullet_order:
        tech.sort(key=lambda s: -_relevance(s, keywords))
    items = []
    if template.skills_style == "grouped":
        if tech:
            items.append("Technical: " + ", ".join(tech))
        if p.skills.interpersonal:
            items.append("Interpersonal: " + ", ".join(p.skills.interpersonal))
        kind = "list"
    else:
        items = tech + p.skills.interpersonal
        kind = "inline"
    sections["skills"] = ResumeSection(key="skills", title=template.title_for("skills"), kind=kind, items=items)

    exp_entries = []
    for i, e in enumerate(p.experience):
        idx = list(range(len(e.bullets)))
        if keywords and options.tailor_bullet_order:
            idx.sort(key=lambda j: -_relevance(e.bullets[j], keywords))
        if options.max_bullets_per_role:
            idx = idx[:options.max_bullets_per_role]
        exp_entries.append(ResumeEntry(
            id=e.id, heading=e.title, subheading=e.employer, location=e.location,
            dates=format_range(e.start_date, e.end_date, e.current, date_style),
            bullets=[e.bullets[j] for j in idx], bullet_sources=[f"experience[{i}].bullets[{j}]" for j in idx],
            source_path=f"experience[{i}]"))
    sections["experience"] = ResumeSection(key="experience", title=template.title_for("experience"), entries=exp_entries)

    proj = []
    for i, pr in enumerate(p.projects):
        bl = ([pr.description] if pr.description else []) + list(pr.bullets)
        srcs = ([f"projects[{i}].description"] if pr.description else []) + [f"projects[{i}].bullets[{j}]" for j in range(len(pr.bullets))]
        proj.append(ResumeEntry(id=pr.id, heading=pr.name, subheading=pr.role,
                                dates=format_range(pr.start_date, pr.end_date, False, date_style),
                                meta="  |  ".join(x for x in (("Technologies: " + ", ".join(pr.technologies)) if pr.technologies else "",
                                                              display_url(pr.link)) if x),
                                bullets=bl, bullet_sources=srcs,
                                source_path=f"projects[{i}]"))
    if keywords and options.tailor_bullet_order:
        proj.sort(key=lambda en: -_relevance(" ".join([en.heading, en.meta] + en.bullets), keywords))
    sections["projects"] = ResumeSection(key="projects", title=template.title_for("projects"), entries=proj)

    edu = []
    for i, ed in enumerate(p.education):
        heading = ed.degree + (f" in {ed.field_of_study}" if ed.field_of_study and ed.field_of_study.lower() not in ed.degree.lower() else "")
        edu.append(ResumeEntry(id=ed.id, heading=heading, subheading=ed.institution, location=ed.location,
                               dates=format_range(ed.start_date, ed.end_date, False, date_style), meta=ed.grade,
                               bullets=list(ed.details), bullet_sources=[f"education[{i}].details[{j}]" for j in range(len(ed.details))],
                               source_path=f"education[{i}]"))
    sections["education"] = ResumeSection(key="education", title=template.title_for("education"), entries=edu)

    certs = []
    for c in p.certifications:
        parts = [c.name] + ([c.issuer] if c.issuer else []) + ([format_date(c.date, date_style)] if c.date else [])
        certs.append(" — ".join(parts[:2]) + (f" ({parts[2]})" if len(parts) > 2 else ""))
    sections["certifications"] = ResumeSection(key="certifications", title=template.title_for("certifications"),
                                               kind="list", items=certs)
    pubs = []
    for pub in p.publications:
        s = ". ".join(x for x in (pub.authors, f"({pub.year})" if pub.year else "", pub.title, pub.venue) if x)
        pubs.append(s.replace(". (", " (").replace("). ", "). "))
    sections["publications"] = ResumeSection(key="publications", title=template.title_for("publications"), kind="list", items=pubs)
    langs = [f"{l.language} ({l.proficiency})" if l.proficiency else l.language for l in p.languages if l.language]
    sections["languages"] = ResumeSection(key="languages", title=template.title_for("languages"), kind="inline", items=langs)
    awards = [" — ".join(x for x in (a.title, a.issuer) if x) + (f" ({format_date(a.date, date_style)})" if a.date else "")
              + (f": {a.description}" if a.description else "") for a in p.awards]
    sections["awards"] = ResumeSection(key="awards", title=template.title_for("awards"), kind="list", items=awards)
    vols = [ResumeEntry(id=v.id, heading=v.role, subheading=v.organization,
                        dates=format_range(v.start_date, v.end_date, False, date_style), bullets=list(v.bullets),
                        bullet_sources=[f"volunteering[{i}].bullets[{j}]" for j in range(len(v.bullets))],
                        source_path=f"volunteering[{i}]") for i, v in enumerate(p.volunteering)]
    sections["volunteering"] = ResumeSection(key="volunteering", title=template.title_for("volunteering"), entries=vols)
    refs = []
    if p.include_referees:
        for r in p.referees:
            if r.permission_confirmed and r.name:
                refs.append(ResumeEntry(heading=r.name, subheading=", ".join(x for x in (r.title, r.organization) if x),
                                        meta=" | ".join(x for x in (r.email, r.phone, r.relationship) if x)))
    sections["referees"] = ResumeSection(key="referees", title=template.title_for("referees"), entries=refs)

    for key in section_order(template, p, options):
        sec = sections[key]
        sec.enabled = key not in options.disabled_sections
        sec.sidebar = template.layout == "sidebar" and key in template.sidebar_sections
        doc.sections.append(sec)
    doc.suggestions = bullet_suggestions(p, matches)
    return doc


def bullet_suggestions(p: CandidateProfile, matches: list[RequirementMatch]) -> list[BulletSuggestion]:
    out: list[BulletSuggestion] = []
    for i, e in enumerate(p.experience):
        for j, b in enumerate(e.bullets):
            if not re.search(r"\d", b) and len(out) < 8:
                out.append(BulletSuggestion(
                    path=f"experience[{i}].bullets[{j}]", text=b, kind="metric",
                    question="Do you know a real, measurable result for this point (e.g. how many, how much, how fast)? "
                             "If so, add it — only if it's accurate."))
    for m in matches:
        if m.status in ("transferable", "needs_clarification"):
            out.append(BulletSuggestion(path="", text=m.requirement, kind="evidence",
                                        question=f"Do you have a concrete example for: “{m.requirement[:120]}”? "
                                                 f"If yes, add it to the relevant role. {m.note}".strip()))
    return out


def draft_resume(p: CandidateProfile, analysis: JobAnalysis | None, matches: list[RequirementMatch],
                 template: TemplateSpec, options: RenderOptions, llm: LLMService | None,
                 feedback: list[str] | None = None) -> tuple[ResumeDocument, list[str]]:
    errors: list[str] = []
    doc = build_document(p, analysis, matches, template, options)
    if llm is None:
        return doc, errors
    bullets = {}
    for sec in doc.sections:
        if sec.key in ("experience", "projects", "volunteering"):
            for en in sec.entries:
                for k, (b, src) in enumerate(zip(en.bullets, en.bullet_sources)):
                    bullets[src] = b
    supported = [m.requirement for m in matches if m.status == "supported"][:12]
    facts = p.model_dump(exclude={"contact", "referees", "target", "skipped_fields", "schema_version"})
    try:
        res = llm.structured(_DraftOut, DRAFTING_PROMPT, {
            "years_experience": f"{int(total_experience_years(p.experience))}",
            "target": p.target.occupation or (analysis.title if analysis else ""),
            "supported": "; ".join(supported) or "none supplied",
            "facts": fence(str(facts), "candidate_data"),
            "bullets": fence("\n".join(f"{k}: {v}" for k, v in bullets.items()), "candidate_data"),
            "feedback": ("Previous draft problems to fix (do not repeat them): " + "; ".join(feedback)) if feedback else "",
        })
    except LLMError as e:
        errors.append(f"AI drafting unavailable ({e.user_message()}) — your corrected wording was used.")
        return doc, errors
    rewrites = {b.id: b.text.strip() for b in res.bullets if b.id in bullets and b.text.strip()}
    for sec in doc.sections:
        if sec.key == "summary" and res.summary.strip() and not p.summary.strip():
            sec.text = res.summary.strip()
        elif sec.key == "summary" and res.summary.strip() and p.summary.strip():
            sec.text = res.summary.strip()
        for en in sec.entries:
            en.bullets = [rewrites.get(src, b) for b, src in zip(en.bullets, en.bullet_sources)]
    doc.generated_with = "llm"
    return doc, errors
