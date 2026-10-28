"""Rule-based extraction used when no LLM provider is configured, and as a
fallback when the provider fails. Conservative: anything uncertain is left
for the candidate to review rather than guessed."""
from __future__ import annotations

import re

from src.models.profile import (Award, CandidateProfile, Certification, Education, Experience,
                                LanguageSkill, Link, Project, Publication, Volunteer)
from src.services.dates import DATE_RANGE_RE, is_present
from src.services.text_utils import EMAIL_RE, PHONE_RE, URL_RE, normalize_ws

SECTION_ALIASES = {
    "summary": ["summary", "professional summary", "profile", "about me", "objective", "career objective",
                "personal statement", "professional profile"],
    "experience": ["experience", "work experience", "professional experience", "employment history",
                   "employment", "work history", "career history", "relevant experience"],
    "education": ["education", "academic background", "qualifications", "academic qualifications",
                  "education and training"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "competencies", "core competencies",
               "skills and tools", "tools", "technologies"],
    "certifications": ["certifications", "certificates", "licenses", "licences", "certifications and training",
                       "training", "courses"],
    "projects": ["projects", "selected projects", "key projects", "academic projects", "portfolio"],
    "publications": ["publications", "research", "papers", "conference papers"],
    "languages": ["languages", "language skills"],
    "awards": ["awards", "honours", "honors", "achievements", "awards and honours"],
    "volunteering": ["volunteering", "volunteer experience", "community involvement", "volunteer work"],
    "references": ["references", "referees"],
}
_ALIAS_TO_KEY = {a: k for k, al in SECTION_ALIASES.items() for a in al}
BULLET_RE = re.compile(r"^\s*(?:[•▪◦●\-–*·]|\d+[.)])\s+")
DEGREE_RE = re.compile(r"\b(B\.?Sc|M\.?Sc|B\.?A|M\.?A|B\.?E|M\.?E|B\.?Tech|M\.?Tech|Ph\.?D|MBA|BBA|MPhil|M\.?Phil|"
                       r"Bachelor|Master|Doctor|Diploma|Associate|Certificate|HND|A[- ]Levels?|BS|MS|BEng|MEng|LLB|MBBS|BSN)\b",
                       re.I)
INSTITUTION_RE = re.compile(r"\b(University|College|Institute|School|Academy|Polytechnic|Universit[éeà]|Hochschule)\b", re.I)


def heading_key(line: str) -> str | None:
    t = re.sub(r"[^A-Za-z &]", "", line).strip().lower()
    if not t or len(t) > 40:
        return None
    return _ALIAS_TO_KEY.get(t)


def split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if current:
                sections[current].append("")
            continue
        key = heading_key(line)
        if key and (line.strip().isupper() or line.strip().istitle() or line.strip().endswith(":") or len(line.split()) <= 4):
            current = key
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
        else:
            header.append(line)
    return header, sections


def extract_contact(text: str, profile: CandidateProfile) -> list[str]:
    """Fill contact details found in text. Returns names of fields filled."""
    filled = []
    c = profile.contact
    if not c.email:
        m = EMAIL_RE.search(text)
        if m:
            c.email = m.group(0); filled.append("email")
    if not c.phone:
        for m in PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 7 <= len(digits) <= 15 and not DATE_RANGE_RE.search(m.group(0)) and not re.fullmatch(r"(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}", m.group(0).strip()):
                c.phone = normalize_ws(m.group(0)); filled.append("phone")
                break
    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,)")
        low = u.lower()
        if "@" in text[max(0, m.start() - 1):m.start()] or "." not in u:
            continue
        if EMAIL_RE.fullmatch(text[max(0, m.start() - 40):m.end()].split()[-1] if text[max(0, m.start() - 40):m.end()].split() else ""):
            continue
        if "linkedin.com" in low and not c.linkedin:
            c.linkedin = u; filled.append("linkedin")
        elif ("github.com" in low or "gitlab.com" in low) and not c.github:
            c.github = u; filled.append("github")
        elif low.startswith(("http", "www.")) and not any(x in low for x in ("linkedin", "github")):
            if not c.portfolio:
                c.portfolio = u; filled.append("portfolio")
            elif u not in [l.url for l in c.other_links]:
                c.other_links.append(Link(label="Link", url=u))
    return filled


def parse_role_line(line: str) -> dict:
    """Parse 'GIS Analyst at Contoso Ltd, Lahore, Jan 2020 - Present' style lines."""
    out = {"title": "", "employer": "", "location": "", "start_date": "", "end_date": "", "current": False}
    s = normalize_ws(BULLET_RE.sub("", line))
    m = DATE_RANGE_RE.search(s)
    if m:
        out["start_date"] = m.group("start").strip()
        end = m.group("end").strip()
        if is_present(end):
            out["current"] = True
        else:
            out["end_date"] = end
        s = (s[:m.start()] + s[m.end():]).strip(" ,|–—-()")
    parts = None
    for sep in (" at ", " @ ", " — ", " – ", " | ", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            parts = [a.strip(" ,|"), b.strip(" ,|")]
            break
    if parts:
        out["title"] = parts[0]
        rest = [p.strip() for p in re.split(r",|\|", parts[1]) if p.strip()]
        if rest:
            out["employer"] = rest[0]
            if len(rest) > 1:
                out["location"] = ", ".join(rest[1:])
    else:
        bits = [p.strip() for p in s.split(",") if p.strip()]
        if bits:
            out["title"] = bits[0]
        if len(bits) > 1:
            out["employer"] = bits[1]
        if len(bits) > 2:
            out["location"] = ", ".join(bits[2:])
    return out


def parse_experience_block(lines: list[str]) -> list[Experience]:
    roles: list[Experience] = []
    pending_header: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if BULLET_RE.match(line):
            text = BULLET_RE.sub("", line).strip()
            if not roles or pending_header:
                roles.append(_role_from_header(pending_header))
                pending_header = []
            roles[-1].bullets.append(text)
            continue
        if DATE_RANGE_RE.search(line) or not roles or pending_header or len(line) < 70:
            if roles and not pending_header and not DATE_RANGE_RE.search(line) and len(line) >= 70:
                roles[-1].bullets.append(line.strip())
                continue
            pending_header.append(line.strip())
            if DATE_RANGE_RE.search(line) and len(pending_header) >= 1 and _header_complete(pending_header):
                roles.append(_role_from_header(pending_header))
                pending_header = []
        else:
            roles[-1].bullets.append(line.strip())
    if pending_header:
        roles.append(_role_from_header(pending_header))
    return [r for r in roles if r.title or r.employer or r.bullets]


def _header_complete(lines: list[str]) -> bool:
    joined = " , ".join(lines)
    p = parse_role_line(joined)
    return bool(p["title"] and p["employer"])


def _role_from_header(lines: list[str]) -> Experience:
    if not lines:
        return Experience()
    if len(lines) >= 2 and not any(s in lines[0] for s in (" at ", " | ", " — ", " – ", " - ", ",")):
        joined = f"{lines[0]} | {' , '.join(lines[1:])}"
    else:
        joined = " , ".join(lines)
    p = parse_role_line(joined)
    return Experience(**p)


def parse_education_block(lines: list[str]) -> list[Education]:
    out: list[Education] = []
    cur: Education | None = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if BULLET_RE.match(s) and cur:
            cur.details.append(BULLET_RE.sub("", s))
            continue
        is_degree = bool(DEGREE_RE.search(s))
        is_inst = bool(INSTITUTION_RE.search(s))
        if is_degree and (cur is None or cur.degree):
            cur = Education(); out.append(cur)
        elif is_inst and cur is not None and cur.institution:
            cur = Education(); out.append(cur)
        elif cur is None:
            cur = Education(); out.append(cur)
        m = DATE_RANGE_RE.search(s)
        if m:
            cur.start_date = cur.start_date or m.group("start")
            cur.end_date = cur.end_date or m.group("end")
            s = (s[:m.start()] + s[m.end():]).strip(" ,|–-()")
        else:
            y = re.search(r"\b(19|20)\d{2}\b", s)
            if y and not cur.end_date:
                cur.end_date = y.group(0)
                s = (s[:y.start()] + s[y.end():]).strip(" ,|–-()")
        g = re.search(r"\b(CGPA|GPA|Grade|Honours|Honors|First Class|Distinction|Merit)\b[^,|]*", s, re.I)
        if g and not cur.grade:
            cur.grade = g.group(0).strip()
            s = s.replace(g.group(0), "").strip(" ,|–-")
        for part in [p.strip() for p in re.split(r",|\||—|–", s) if p.strip()]:
            if INSTITUTION_RE.search(part) and not cur.institution:
                cur.institution = part
            elif DEGREE_RE.search(part) and not cur.degree:
                if " in " in part:
                    d, f = part.split(" in ", 1)
                    cur.degree, cur.field_of_study = d.strip(), f.strip()
                else:
                    cur.degree = part
            elif not cur.location and cur.institution and len(part.split()) <= 3:
                cur.location = part
            elif not cur.degree:
                cur.degree = part
    return [e for e in out if e.degree or e.institution]


def split_list(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        s = BULLET_RE.sub("", line).strip()
        if not s:
            continue
        if ":" in s and len(s.split(":", 1)[0].split()) <= 3:
            s = s.split(":", 1)[1]
        for part in re.split(r"[,;|•·]", s):
            p = part.strip(" .")
            if p and len(p) <= 60:
                items.append(p)
    seen, out = set(), []
    for i in items:
        if i.lower() not in seen:
            seen.add(i.lower()); out.append(i)
    return out


SOFT_SKILLS = {"communication", "teamwork", "leadership", "problem solving", "problem-solving", "time management",
               "collaboration", "adaptability", "critical thinking", "attention to detail", "stakeholder management",
               "negotiation", "presentation", "mentoring", "organisation", "organization", "creativity",
               "public speaking", "customer service", "conflict resolution", "interpersonal skills"}


def parse_resume_text(text: str) -> CandidateProfile:
    profile = CandidateProfile()
    header, sections = split_sections(text)
    extract_contact(text, profile)
    for line in header:
        s = line.strip()
        if not s or EMAIL_RE.search(s) or URL_RE.fullmatch(s) or sum(ch.isdigit() for ch in s) > 5:
            continue
        if not profile.full_name and len(s.split()) <= 5 and not heading_key(s):
            profile.full_name = s.title() if s.isupper() else s
            continue
        if profile.full_name and not profile.headline and len(s) <= 90 and "|" not in s:
            profile.headline = s
        elif profile.full_name and "," in s and len(s) <= 60 and not profile.contact.city:
            bits = [b.strip() for b in s.split(",")]
            profile.contact.city, profile.contact.country = bits[0], bits[-1] if len(bits) > 1 else ""
    if "summary" in sections:
        profile.summary = normalize_ws(" ".join(l for l in sections["summary"] if l.strip()))
    if "experience" in sections:
        profile.experience = parse_experience_block(sections["experience"])
    if "education" in sections:
        profile.education = parse_education_block(sections["education"])
    if "skills" in sections:
        for item in split_list(sections["skills"]):
            (profile.skills.interpersonal if item.lower() in SOFT_SKILLS else profile.skills.technical).append(item)
    if "certifications" in sections:
        for item in [BULLET_RE.sub("", l).strip() for l in sections["certifications"] if l.strip()]:
            y = re.search(r"\b(19|20)\d{2}\b", item)
            name = re.sub(r"[,(–-]*\s*\b(19|20)\d{2}\b\)?", "", item).strip(" ,–-")
            issuer = ""
            if " — " in name or " - " in name:
                name, issuer = re.split(r" — | - ", name, 1)
            profile.certifications.append(Certification(name=name.strip(), issuer=issuer.strip(), date=y.group(0) if y else ""))
    if "projects" in sections:
        cur = None
        for l in sections["projects"]:
            if not l.strip():
                continue
            if BULLET_RE.match(l) and cur is not None:
                cur.bullets.append(BULLET_RE.sub("", l).strip())
            else:
                cur = Project(name=BULLET_RE.sub("", l).strip()[:120]); profile.projects.append(cur)
    if "publications" in sections:
        for l in sections["publications"]:
            s = BULLET_RE.sub("", l).strip()
            if s:
                y = re.search(r"\b(19|20)\d{2}\b", s)
                profile.publications.append(Publication(title=s, year=y.group(0) if y else ""))
    if "languages" in sections:
        for item in split_list(sections["languages"]):
            m = re.match(r"(.+?)\s*[(\-–:]\s*(.+?)\)?$", item)
            profile.languages.append(LanguageSkill(language=m.group(1).strip(), proficiency=m.group(2).strip())
                                     if m else LanguageSkill(language=item))
    if "awards" in sections:
        for l in sections["awards"]:
            s = BULLET_RE.sub("", l).strip()
            if s:
                y = re.search(r"\b(19|20)\d{2}\b", s)
                profile.awards.append(Award(title=s, date=y.group(0) if y else ""))
    if "volunteering" in sections:
        vols = parse_experience_block(sections["volunteering"])
        profile.volunteering = [Volunteer(role=v.title, organization=v.employer, start_date=v.start_date,
                                          end_date=v.end_date or ("Present" if v.current else ""), bullets=v.bullets)
                                for v in vols]
    return profile
