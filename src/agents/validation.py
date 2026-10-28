"""Profile validation: field checks, contradictions and completion progress."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.profile import CandidateProfile
from src.services.dates import range_problem
from src.services.text_utils import is_valid_email, link_problem


class Question(BaseModel):
    path: str
    label: str
    current: str = ""
    help: str = ""


class Issue(BaseModel):
    path: str
    message: str
    severity: Literal["error", "warning", "info"] = "warning"
    blocking: bool = False
    questions: list[Question] = Field(default_factory=list)
    action_only: bool = False   # must be fixed in the Add-information step


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)
    completion: int = 0
    sections: dict[str, str] = Field(default_factory=dict)   # key -> complete | partial | missing | skipped
    missing_for_export: list[str] = Field(default_factory=list)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]


def _entry_label(kind: str, i: int, a: str, b: str) -> str:
    inner = " — ".join(x for x in (a, b) if x) or "untitled"
    return f"{kind} {i + 1} ({inner})"


def validate_profile(p: CandidateProfile, unverified: list[str] | None = None) -> ValidationReport:
    r = ValidationReport()
    c = p.contact
    add = r.issues.append

    if not p.full_name.strip():
        add(Issue(path="full_name", message="Your name is missing.", severity="error", blocking=True,
                  questions=[Question(path="full_name", label="Full name")]))
    if not c.email and not c.phone:
        add(Issue(path="contact.email", message="Add at least one way for employers to contact you.",
                  severity="error", blocking=True,
                  questions=[Question(path="contact.email", label="Email address")]))
    if c.email and not is_valid_email(c.email):
        add(Issue(path="contact.email", message=f"The email address '{c.email}' looks malformed.",
                  severity="error", blocking=True,
                  questions=[Question(path="contact.email", label="Corrected email address", current=c.email)]))
    if c.phone:
        digits = sum(ch.isdigit() for ch in c.phone)
        if digits < 7 or digits > 15:
            add(Issue(path="contact.phone", message=f"The phone number '{c.phone}' has {digits} digits; please check it.",
                      severity="warning",
                      questions=[Question(path="contact.phone", label="Phone number", current=c.phone)]))
    for fld in ("linkedin", "github", "portfolio"):
        url = getattr(c, fld)
        prob = link_problem(url)
        if prob:
            add(Issue(path=f"contact.{fld}", message=f"The {fld.title()} link '{url}' {prob}.", severity="warning",
                      questions=[Question(path=f"contact.{fld}", label=f"{fld.title()} URL", current=url)]))
    for i, l in enumerate(c.other_links):
        prob = link_problem(l.url)
        if prob:
            add(Issue(path=f"contact.other_links[{i}].url", message=f"The link '{l.url}' {prob}.", severity="warning"))

    if not (p.experience or p.education or p.projects):
        add(Issue(path="experience", severity="error", blocking=True, action_only=True,
                  message="Add at least one role, qualification or project before generating a resume."))

    for i, e in enumerate(p.experience):
        lbl = _entry_label("Experience", i, e.title, e.employer)
        if not e.title:
            add(Issue(path=f"experience[{i}].title", message=f"{lbl} has no job title.", severity="error", blocking=True,
                      questions=[Question(path=f"experience[{i}].title", label=f"Job title for {lbl}")]))
        if not e.employer:
            add(Issue(path=f"experience[{i}].employer", message=f"{lbl} has no employer name.", severity="error",
                      blocking=True, questions=[Question(path=f"experience[{i}].employer", label=f"Employer for {lbl}",
                                                         help="Use 'Self-employed' or 'Freelance' if applicable.")]))
        prob = range_problem(e.start_date, e.end_date, e.current)
        if prob:
            blocking = "future" not in prob
            add(Issue(path=f"experience[{i}].start_date", message=f"{lbl} {prob}. Please confirm the dates.",
                      severity="error" if blocking else "warning", blocking=blocking,
                      questions=[Question(path=f"experience[{i}].start_date", label="Start date", current=e.start_date,
                                          help="e.g. Mar 2021 or 2021"),
                                 Question(path=f"experience[{i}].end_date", label="End date", current=e.end_date,
                                          help="Leave as 'Present' for a current role")]))
        if not e.start_date:
            add(Issue(path=f"experience[{i}].start_date", message=f"{lbl} has no dates.", severity="warning",
                      questions=[Question(path=f"experience[{i}].start_date", label="Start date"),
                                 Question(path=f"experience[{i}].end_date", label="End date (or Present)")]))
        if not e.bullets:
            add(Issue(path=f"experience[{i}].bullets", message=f"{lbl} has no achievements or responsibilities.",
                      severity="warning"))

    for i, ed in enumerate(p.education):
        lbl = _entry_label("Education", i, ed.degree, ed.institution)
        if not ed.institution:
            add(Issue(path=f"education[{i}].institution", message=f"{lbl} is missing the institution.", severity="error",
                      blocking=True, questions=[Question(path=f"education[{i}].institution", label=f"Institution for {lbl}")]))
        if not ed.degree:
            add(Issue(path=f"education[{i}].degree", message=f"{lbl} is missing the qualification name.",
                      severity="error", blocking=True,
                      questions=[Question(path=f"education[{i}].degree", label=f"Qualification for {lbl}")]))
        prob = range_problem(ed.start_date, ed.end_date)
        if prob and "future" not in prob:
            add(Issue(path=f"education[{i}].start_date", message=f"{lbl} {prob}.", severity="error", blocking=True,
                      questions=[Question(path=f"education[{i}].start_date", label="Start date", current=ed.start_date),
                                 Question(path=f"education[{i}].end_date", label="End / expected date", current=ed.end_date)]))

    for i, cert in enumerate(p.certifications):
        if cert.name and not cert.issuer:
            add(Issue(path=f"certifications[{i}].issuer", message=f"Certification '{cert.name}' has no issuer.",
                      severity="info"))
    if p.include_referees:
        for i, ref in enumerate(p.referees):
            if not ref.permission_confirmed:
                add(Issue(path=f"referees[{i}].permission_confirmed", severity="warning",
                          message=f"Referee '{ref.name or i + 1}' will be omitted until you confirm you have their permission."))
    for path in unverified or []:
        add(Issue(path=path, severity="warning",
                  message="Imported automatically and could not be matched word-for-word to your document — please confirm."))

    for i, role in enumerate(p.experience):
        for field, limit in (("title", 180), ("employer", 180), ("location", 120)):
            value = getattr(role, field)
            if len(value) > limit or "\n" in value or "\x00" in value:
                add(Issue(path=f"experience[{i}].{field}", severity="error", blocking=True, action_only=True,
                          message=f"Role {i + 1}: {field} contains a paragraph or imported bullet text. "
                                  "Review this role in Add information: keep its heading/employer/location short "
                                  "and move responsibilities into separate achievement lines."))
    if len(p.skills.technical) > 65 or any(len(v) > 160 for v in p.skills.technical):
        add(Issue(path="skills.technical", severity="error", blocking=True, action_only=True,
                  message="Skills contains unusually long text or too many imported items. Review Skills in "
                          "Add information; keep tools/competencies here and move projects, roles and courses "
                          "to their own sections before generating."))

    # ------------------------------------------------------------ completion
    skipped = set(p.skipped_fields)
    checks = [
        ("Name", 10, bool(p.full_name), "full_name"),
        ("Email", 8, bool(c.email) and is_valid_email(c.email), "contact"),
        ("Phone", 5, bool(c.phone), "contact"),
        ("Location", 4, bool(c.city or c.country), "location"),
        ("Headline", 4, bool(p.headline), "headline"),
        ("Target job", 7, bool(p.target.occupation), "target"),
        ("Experience", 15, bool(p.experience), "experience"),
        ("Achievements", 10, bool(p.experience) and all(e.bullets for e in p.experience), "experience_bullets"),
        ("Education", 12, bool(p.education), "education"),
        ("Skills", 10, bool(p.skills.technical), "skills"),
        ("Summary", 5, bool(p.summary), "summary"),
        ("Links", 3, bool(c.linkedin or c.github or c.portfolio), "links"),
        ("Projects / certifications / languages", 7,
         bool(p.projects or p.certifications or p.languages), "projects"),
    ]
    got = 0
    for label, w, ok, key in checks:
        if ok or key in skipped or (key in ("experience", "experience_bullets") and "experience" in skipped):
            got += w
        else:
            r.missing_for_export.append(label)
    r.completion = int(round(got))
    r.sections = {
        "Contact": "complete" if c.email and c.phone else ("partial" if c.email or c.phone else "missing"),
        "Summary": "complete" if p.summary else ("skipped" if "summary" in skipped else "missing"),
        "Experience": ("complete" if p.experience and all(e.bullets for e in p.experience) else
                       "partial" if p.experience else "skipped" if "experience" in skipped else "missing"),
        "Education": "complete" if p.education else "missing",
        "Skills": "complete" if p.skills.technical else "missing",
        "Projects": "complete" if p.projects else ("skipped" if "projects" in skipped else "missing"),
        "Certifications": "complete" if p.certifications else ("skipped" if "certifications" in skipped else "missing"),
        "Languages": "complete" if p.languages else ("skipped" if "languages" in skipped else "missing"),
    }
    return r


def apply_answers(p: CandidateProfile, answers: dict[str, str]) -> CandidateProfile:
    """Apply clarification answers (path -> text) to a copy of the profile."""
    from src.models.paths import PathError, set_path

    data = p.model_dump()
    for path, value in answers.items():
        if path.startswith("__"):
            continue
        try:
            set_path(data, path, value.strip() if isinstance(value, str) else value)
        except PathError:
            continue
        if path.endswith("end_date") and isinstance(value, str) and value.strip().lower() in ("present", "current"):
            idx_path = path.rsplit(".", 1)[0]
            try:
                set_path(data, idx_path + ".current", True)
                set_path(data, path, "")
            except PathError:
                pass
        elif path.endswith("end_date") and isinstance(value, str) and value.strip() and path.startswith("experience"):
            try:
                set_path(data, path.rsplit(".", 1)[0] + ".current", False)
            except PathError:
                pass
    return CandidateProfile.model_validate(data)
