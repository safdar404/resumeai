from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Importance = Literal["required", "preferred"]
MatchStatus = Literal["supported", "transferable", "not_demonstrated", "needs_clarification"]

STATUS_LABELS = {
    "supported": "Supported by evidence",
    "transferable": "Transferable experience",
    "not_demonstrated": "Not demonstrated",
    "needs_clarification": "Needs clarification",
}


class JobRequirement(BaseModel):
    id: str
    text: str
    keywords: list[str] = Field(default_factory=list)
    importance: Importance = "required"
    category: str = "skill"           # skill | experience | education | certification | other
    years: int | None = None


class JobAnalysis(BaseModel):
    title: str = ""
    sector: str = "general"
    seniority: str = ""
    requirements: list[JobRequirement] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    method: Literal["rules", "llm"] = "rules"


class Evidence(BaseModel):
    id: str
    text: str
    source: str  # human label e.g. "GIS Analyst — Contoso (bullet 2)"


class RequirementMatch(BaseModel):
    requirement_id: str
    requirement: str
    importance: Importance = "required"
    status: MatchStatus
    strength: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    note: str = ""
    method: Literal["rules", "llm-estimate"] = "rules"
