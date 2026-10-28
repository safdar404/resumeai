"""Deterministic conversational intake: chooses the next focused question and
applies answers to the field that was asked. Used offline and as the source
of question selection in LLM mode (so questions are never repeated)."""
from __future__ import annotations

import re

from src.models.profile import CandidateProfile, Certification, Education, Experience, LanguageSkill, Project
from src.services.heuristic_parser import (BULLET_RE, DEGREE_RE, INSTITUTION_RE, SOFT_SKILLS, extract_contact,
                                           parse_education_block, parse_role_line, split_list)
from src.services.text_utils import normalize_ws

SKIP_WORDS = {"skip", "none", "no", "n/a", "na", "nothing", "not applicable", "pass", "later", "-"}

# (field key, question, optional?)
FLOW: list[tuple[str, str, bool]] = [
    ("full_name", "Let's start simple — what is your full name as it should appear on your resume?", False),
    ("target", "Which job or occupation are you targeting? (e.g. *GIS Analyst*, *Data Scientist*, *Staff Nurse*)", False),
    ("contact", "What email address and phone number should employers use? You can share both in one message.", False),
    ("location", "Which city and country are you based in? (e.g. *Islamabad, Pakistan*)", True),
    ("headline", "In a few words, how would you describe yourself professionally? (e.g. *GIS Analyst specialising in land-cover mapping*)", True),
    ("experience", "Tell me about your most recent role in one line: **job title, employer, location, start – end dates**. "
                   "Example: *GIS Analyst at Contoso Ltd, Lahore, Mar 2021 – Present*. Type *none* if you have no work experience yet.", True),
    ("experience_bullets", "What did you do or achieve in that role? Write 2–5 points, one per line. "
                           "Include real results only if you know them (numbers, scale, time saved).", True),
    ("more_experience", "Do you have another role to add? Share it in the same format, or type *no*.", True),
    ("education", "What is your highest qualification? Example: *BSc in Geography, University of Punjab, 2016 – 2020, CGPA 3.6/4*.", False),
    ("skills", "List your technical skills and tools, separated by commas.", False),
    ("interpersonal", "Any interpersonal skills you want to highlight (e.g. stakeholder communication, mentoring)? Type *skip* to move on.", True),
    ("projects", "Any notable projects? Give the project name and a one-line description, one project per line — or *skip*.", True),
    ("certifications", "Any certifications or training? One per line, e.g. *Esri Technical Certification — Esri, 2023* — or *skip*.", True),
    ("languages", "Which languages do you speak, and how well? e.g. *English (fluent), Urdu (native)* — or *skip*.", True),
    ("links", "Share any LinkedIn, GitHub or portfolio links — or *skip*.", True),
    ("summary", "Would you like to write your own short professional summary? Paste it, or type *skip* and I'll draft one only from the facts you've given.", True),
    ("job_description", "Finally, paste the job description you're applying for so I can tailor the resume — or *skip*.", True),
]
FLOW_KEYS = [k for k, _, _ in FLOW]


def is_skip(text: str) -> bool:
    return normalize_ws(text).lower().strip(".!") in SKIP_WORDS


def field_filled(p: CandidateProfile, key: str) -> bool:
    c = p.contact
    return {
        "full_name": bool(p.full_name),
        "target": bool(p.target.occupation),
        "contact": bool(c.email and c.phone),
        "location": bool(c.city or c.country),
        "headline": bool(p.headline),
        "experience": bool(p.experience),
        "experience_bullets": bool(p.experience) and all(len(e.bullets) >= 1 for e in p.experience),
        "more_experience": False,
        "education": bool(p.education),
        "skills": bool(p.skills.technical),
        "interpersonal": bool(p.skills.interpersonal),
        "projects": bool(p.projects),
        "certifications": bool(p.certifications),
        "languages": bool(p.languages),
        "links": bool(c.linkedin or c.github or c.portfolio or c.other_links),
        "summary": bool(p.summary),
        "job_description": bool(p.target.job_description),
    }.get(key, False)


def next_question(p: CandidateProfile, asked: dict[str, int]) -> tuple[str | None, str]:
    """Return (field_key, question) for the first unfilled, un-skipped field.

    Each field is asked at most twice (second time with a format hint), so
    the assistant never loops on information already provided or declined.
    """
    for key, question, optional in FLOW:
        if key in p.skipped_fields or field_filled(p, key):
            continue
        if key == "experience_bullets" and (not p.experience or "experience" in p.skipped_fields):
            continue
        if key == "more_experience" and (not p.experience or asked.get(key, 0) >= 1):
            continue
        n = asked.get(key, 0)
        if n >= 2:
            continue
        if n == 1:
            return key, "I couldn't quite capture that. " + question + " (Type *skip* to move on.)"
        return key, question
    return None, ""


def apply_answer(p: CandidateProfile, key: str | None, text: str) -> list[str]:
    """Apply a chat answer to the asked field. Returns notes on what was captured."""
    notes: list[str] = []
    text = text.strip()
    if not text:
        return notes
    filled = extract_contact(text, p)
    if filled:
        notes.append("captured " + ", ".join(filled))
    if key is None:
        return notes
    if is_skip(text):
        if key in ("more_experience",):
            p.skipped_fields.append(key)
            return notes + ["no more roles"]
        if key not in p.skipped_fields:
            p.skipped_fields.append(key)
        return notes + [f"skipped {key.replace('_', ' ')}"]
    lines = [l for l in text.splitlines() if l.strip()]
    if key == "full_name":
        name = normalize_ws(re.sub(r"^(my name is|i am|i'm|name:)\s*", "", lines[0], flags=re.I)).strip(" .")
        if 1 <= len(name.split()) <= 6 and not any(ch.isdigit() for ch in name) and "@" not in name:
            p.full_name = name
            notes.append(f"name: {name}")
    elif key == "target":
        p.target.occupation = normalize_ws(re.sub(r"^(i('m| am) (targeting|looking for|applying for)|target:)\s*", "", lines[0], flags=re.I)).strip(" .")
        notes.append(f"target: {p.target.occupation}")
    elif key == "contact":
        pass  # handled by extract_contact
    elif key == "location":
        bits = [b.strip(" .") for b in re.split(r",", lines[0]) if b.strip()]
        if bits:
            p.contact.city = bits[0]
            p.contact.country = bits[-1] if len(bits) > 1 else p.contact.country
            notes.append("location saved")
    elif key == "headline":
        p.headline = normalize_ws(lines[0]).strip(" .")
        notes.append("headline saved")
    elif key in ("experience", "more_experience"):
        if key == "more_experience" and normalize_ws(text).lower() in ("yes", "y"):
            return notes
        role = parse_role_line(lines[0])
        if role["title"] or role["employer"]:
            e = Experience(**role)
            for l in lines[1:]:
                e.bullets.append(BULLET_RE.sub("", l).strip())
            p.experience.append(e)
            notes.append(f"role: {e.title or '?'} — {e.employer or '?'}")
            if key == "more_experience":
                # allow asking again for yet another role
                pass
    elif key == "experience_bullets":
        target = next((e for e in reversed(p.experience) if not e.bullets), p.experience[-1] if p.experience else None)
        if target is not None:
            pts = [BULLET_RE.sub("", l).strip() for l in lines]
            if len(pts) == 1 and ";" in pts[0]:
                pts = [x.strip() for x in pts[0].split(";") if x.strip()]
            target.bullets.extend(x for x in pts if x)
            notes.append(f"added {len(pts)} point(s) to {target.title or 'the role'}")
    elif key == "education":
        eds = parse_education_block(lines if len(lines) > 1 else [lines[0]])
        if not eds and (DEGREE_RE.search(text) or INSTITUTION_RE.search(text)):
            eds = [Education(degree=lines[0])]
        p.education.extend(eds)
        if eds:
            notes.append(f"education: {eds[0].degree or eds[0].institution}")
    elif key in ("skills", "interpersonal"):
        items = split_list(lines)
        for it in items:
            if key == "interpersonal" or it.lower() in SOFT_SKILLS:
                if it not in p.skills.interpersonal:
                    p.skills.interpersonal.append(it)
            elif it not in p.skills.technical:
                p.skills.technical.append(it)
        notes.append(f"{len(items)} skill(s) saved")
    elif key == "projects":
        for l in lines:
            s = BULLET_RE.sub("", l).strip()
            name, _, desc = s.partition(" - ") if " - " in s else s.partition(":")
            p.projects.append(Project(name=name.strip(), description=desc.strip()))
        notes.append(f"{len(lines)} project(s) saved")
    elif key == "certifications":
        for l in lines:
            s = BULLET_RE.sub("", l).strip()
            y = re.search(r"\b(19|20)\d{2}\b", s)
            s2 = re.sub(r",?\s*\b(19|20)\d{2}\b", "", s).strip(" ,")
            name, issuer = (re.split(r"\s+[—–-]\s+", s2, maxsplit=1) + [""])[:2]
            p.certifications.append(Certification(name=name.strip(), issuer=issuer.strip(), date=y.group(0) if y else ""))
        notes.append(f"{len(lines)} certification(s) saved")
    elif key == "languages":
        for item in split_list(lines):
            m = re.match(r"(.+?)\s*\((.+)\)$", item)
            p.languages.append(LanguageSkill(language=m.group(1).strip(), proficiency=m.group(2).strip()) if m
                               else LanguageSkill(language=item))
        notes.append("languages saved")
    elif key == "links":
        if not filled:
            notes.append("no valid links found")
    elif key == "summary":
        p.summary = normalize_ws(text)
        notes.append("summary saved")
    elif key == "job_description":
        p.target.job_description = text[:20000]
        notes.append("job description saved")
    return notes
