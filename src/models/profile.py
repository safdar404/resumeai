"""Validated candidate profile — the single source of truth shared by chat,
forms, uploads and the LangGraph workflow."""
from __future__ import annotations

import uuid
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0"

CareerStage = Literal[
    "graduate", "early", "mid", "senior", "executive", "career_changer", "researcher"
]
CAREER_STAGES: dict[str, str] = {
    "graduate": "Fresh graduate / student",
    "early": "Early career (1-3 years)",
    "mid": "Mid-level professional",
    "senior": "Senior / lead",
    "executive": "Executive / director",
    "career_changer": "Career changer",
    "researcher": "Researcher / academic",
}


def new_id() -> str:
    return uuid.uuid4().hex[:8]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_default(cls, v, info):
        # LLM / JSON inputs sometimes send null for strings and lists.
        if v is None:
            fld = cls.model_fields.get(info.field_name)
            if fld is not None and fld.annotation is str:
                return ""
            if fld is not None and str(fld.annotation).startswith("list"):
                return []
        return v


class Link(_Base):
    label: str = ""
    url: str = ""


class Contact(_Base):
    email: str = ""
    phone: str = ""
    city: str = ""
    country: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    other_links: list[Link] = Field(default_factory=list)


class Experience(_Base):
    id: str = Field(default_factory=new_id)
    title: str = ""
    employer: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    current: bool = False
    bullets: list[str] = Field(default_factory=list)


class Education(_Base):
    id: str = Field(default_factory=new_id)
    degree: str = ""
    field_of_study: str = ""
    institution: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    details: list[str] = Field(default_factory=list)


class Skills(_Base):
    technical: list[str] = Field(default_factory=list)
    interpersonal: list[str] = Field(default_factory=list)


class Certification(_Base):
    id: str = Field(default_factory=new_id)
    name: str = ""
    issuer: str = ""
    date: str = ""
    credential_id: str = ""


class Project(_Base):
    id: str = Field(default_factory=new_id)
    name: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    link: str = ""


class Publication(_Base):
    id: str = Field(default_factory=new_id)
    title: str = ""
    authors: str = ""
    venue: str = ""
    year: str = ""
    link: str = ""


class LanguageSkill(_Base):
    language: str = ""
    proficiency: str = ""


class Award(_Base):
    id: str = Field(default_factory=new_id)
    title: str = ""
    issuer: str = ""
    date: str = ""
    description: str = ""


class Volunteer(_Base):
    id: str = Field(default_factory=new_id)
    role: str = ""
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    bullets: list[str] = Field(default_factory=list)


class Referee(_Base):
    name: str = ""
    title: str = ""
    organization: str = ""
    email: str = ""
    phone: str = ""
    relationship: str = ""
    permission_confirmed: bool = False


class TargetJob(_Base):
    occupation: str = ""
    sector: str = ""
    seniority: str = ""
    location: str = ""
    job_description: str = ""


class CandidateProfile(_Base):
    schema_version: str = SCHEMA_VERSION
    full_name: str = ""
    headline: str = ""
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    languages: list[LanguageSkill] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    volunteering: list[Volunteer] = Field(default_factory=list)
    referees: list[Referee] = Field(default_factory=list)
    include_referees: bool = False
    career_stage: CareerStage = "mid"
    target: TargetJob = Field(default_factory=TargetJob)
    skipped_fields: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    def is_empty(self) -> bool:
        return not (self.full_name or self.experience or self.education or self.skills.technical)

    def prose_fields(self) -> Iterator[tuple[str, str]]:
        """Yield (path, text) for free-text fields eligible for language correction."""
        if self.headline:
            yield "headline", self.headline
        if self.summary:
            yield "summary", self.summary
        for i, e in enumerate(self.experience):
            for j, b in enumerate(e.bullets):
                yield f"experience[{i}].bullets[{j}]", b
        for i, ed in enumerate(self.education):
            for j, d in enumerate(ed.details):
                yield f"education[{i}].details[{j}]", d
        for i, p in enumerate(self.projects):
            if p.description:
                yield f"projects[{i}].description", p.description
            for j, b in enumerate(p.bullets):
                yield f"projects[{i}].bullets[{j}]", b
        for i, a in enumerate(self.awards):
            if a.description:
                yield f"awards[{i}].description", a.description
        for i, v in enumerate(self.volunteering):
            for j, b in enumerate(v.bullets):
                yield f"volunteering[{i}].bullets[{j}]", b

    def protected_terms(self) -> set[str]:
        """Proper nouns and technical terms that correction must never alter."""
        terms: set[str] = set()

        def add(text: str) -> None:
            for tok in text.replace("/", " ").replace(",", " ").split():
                tok = tok.strip("()[]{}.;:")
                if tok:
                    terms.add(tok.lower())

        add(self.full_name)
        for e in self.experience:
            add(e.employer); add(e.location)
        for ed in self.education:
            add(ed.institution); add(ed.location)
        for c in self.certifications:
            add(c.name); add(c.issuer)
        for p in self.projects:
            add(p.name)
            for t in p.technologies:
                add(t)
        for s in self.skills.technical:
            add(s)
        for pub in self.publications:
            add(pub.venue)
        add(self.contact.city); add(self.contact.country)
        return terms

    def corpus(self) -> str:
        """All candidate-supplied text; used to verify that output is supported."""
        data = self.model_dump(exclude={"target", "skipped_fields", "schema_version"})
        parts: list[str] = []

        def walk(v):
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, dict):
                for k, x in v.items():
                    if k != "id":
                        walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)

        walk(data)
        return "\n".join(p for p in parts if p)
