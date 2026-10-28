"""Layout planning: estimate fit and prepare low-priority trimming suggestions.
Nothing is removed automatically — the candidate decides."""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.profile import CandidateProfile
from src.models.resume import ResumeDocument
from src.services.dates import parse_date, today
from src.templates.registry import RenderOptions, TemplateSpec

LOW_PRIORITY = ["volunteering", "awards", "languages", "publications", "referees", "projects", "certifications"]


class LayoutPlan(BaseModel):
    page_size: str = "A4"
    page_target: str = "1"
    max_pages: int | None = 1
    estimated_lines: int = 0
    capacity_lines: int = 0
    start_density: int = 0
    suggestions: list[str] = Field(default_factory=list)


def _lines(text: str, chars_per_line: int = 95) -> int:
    return max(1, -(-len(text) // chars_per_line)) if text else 0


def estimate_lines(doc: ResumeDocument) -> int:
    n = 4
    for s in doc.enabled_sections():
        n += 2
        n += _lines(s.text)
        n += _lines(", ".join(s.items)) if s.kind == "inline" else sum(_lines(i) for i in s.items)
        for e in s.entries:
            n += 1 + (1 if e.meta else 0) + sum(_lines(b, 88) for b in e.bullets)
    return n


def plan_layout(doc: ResumeDocument, p: CandidateProfile, template: TemplateSpec, options: RenderOptions) -> LayoutPlan:
    max_pages = None if options.page_target == "academic" else int(options.page_target)
    capacity = 58 if options.page_size == "A4" else 55
    est = estimate_lines(doc)
    plan = LayoutPlan(page_size=options.page_size, page_target=options.page_target, max_pages=max_pages,
                      estimated_lines=est, capacity_lines=capacity * (max_pages or 99))
    if max_pages and est > capacity * max_pages:
        plan.start_density = 1 if est < capacity * max_pages * 1.15 else 2
        plan.suggestions = fit_suggestions(doc, p, max_pages)
    return plan


def fit_suggestions(doc: ResumeDocument, p: CandidateProfile, max_pages: int | None) -> list[str]:
    out = []
    long_roles = [e for s in doc.enabled_sections() if s.key == "experience" for e in s.entries if len(e.bullets) > 5]
    if long_roles:
        out.append("Limit older roles to their 3–5 most relevant points (Edit step → ‘Max points per role’). "
                   f"Roles with more than five points: {', '.join(e.heading for e in long_roles[:3])}.")
    y, _ = today()
    old = [e for e in p.experience if (parse_date(e.end_date) or (y, None))[0] < y - 12 and not e.current]
    if old:
        out.append(f"Consider summarising roles that ended over 12 years ago ({', '.join(e.title for e in old[:3])}).")
    present = [s.key for s in doc.enabled_sections()]
    low = [k for k in LOW_PRIORITY if k in present and k != "projects" or (k == "projects" and p.experience and k in present)]
    if low:
        out.append("Lower-priority sections you could hide for this application: " + ", ".join(low[:4]) + ".")
    wordy = [b for s in doc.enabled_sections() for e in s.entries for b in e.bullets if len(b.split()) > 32]
    if wordy:
        out.append(f"{len(wordy)} point(s) exceed ~32 words; shorten repetitive wording in the Edit step.")
    if max_pages == 1:
        out.append("Or choose a two-page target if your experience genuinely needs it.")
    return out
