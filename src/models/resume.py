"""Structured resume document — rendered identically to PDF and DOCX."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResumeEntry(BaseModel):
    id: str = ""
    heading: str = ""          # job title / degree / project name
    subheading: str = ""       # employer / institution
    location: str = ""
    dates: str = ""
    meta: str = ""             # grade, technologies, credential id ...
    bullets: list[str] = Field(default_factory=list)
    source_path: str = ""      # profile path the entry came from
    bullet_sources: list[str] = Field(default_factory=list)  # profile path per bullet


class ResumeSection(BaseModel):
    key: str
    title: str
    kind: Literal["text", "entries", "list", "inline"] = "entries"
    text: str = ""
    entries: list[ResumeEntry] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    enabled: bool = True
    sidebar: bool = False      # placed in sidebar for sidebar templates


class BulletSuggestion(BaseModel):
    path: str
    text: str
    question: str
    kind: Literal["metric", "evidence", "wording"] = "metric"


class ResumeDocument(BaseModel):
    name: str = ""
    headline: str = ""
    contact_items: list[str] = Field(default_factory=list)
    sections: list[ResumeSection] = Field(default_factory=list)
    generated_with: Literal["rules", "llm"] = "rules"
    suggestions: list[BulletSuggestion] = Field(default_factory=list)
    user_edited_paths: list[str] = Field(default_factory=list)

    def section(self, key: str) -> ResumeSection | None:
        return next((s for s in self.sections if s.key == key), None)

    def enabled_sections(self) -> list[ResumeSection]:
        return [s for s in self.sections if s.enabled and _has_content(s)]

    def plain_text(self) -> str:
        lines = [self.name, self.headline, " | ".join(self.contact_items)]
        for s in self.enabled_sections():
            lines.append(s.title)
            if s.text:
                lines.append(s.text)
            lines.extend(s.items)
            for e in s.entries:
                lines.append(" ".join(x for x in [e.heading, e.subheading, e.location, e.dates, e.meta] if x))
                lines.extend(e.bullets)
        return "\n".join(l for l in lines if l)


def _has_content(s: ResumeSection) -> bool:
    return bool(s.text.strip() or s.items or s.entries)
