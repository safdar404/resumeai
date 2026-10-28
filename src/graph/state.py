"""Typed LangGraph state. Everything is JSON/msgpack-serialisable so it can be
stored by the checkpointer (bytes are allowed)."""
from __future__ import annotations

from typing import Literal, Optional, TypedDict


class ResumeState(TypedDict, total=False):
    mode: Literal["intake", "generate", "rerender"]
    input_kind: Literal["chat", "document"]
    raw_input: str
    asked_field: Optional[str]
    asked_counts: dict
    profile: dict
    unverified: list
    validation: dict
    corrections: list
    checked_fields: dict
    rejected: list
    intake_notes: list
    assistant_message: str
    next_field: Optional[str]
    template_id: str
    options: dict
    job_analysis: Optional[dict]
    matches: list
    draft: Optional[dict]
    review: Optional[dict]
    draft_attempts: int
    review_feedback: list
    clarification_rounds: int
    score: Optional[dict]
    layout: Optional[dict]
    render_info: Optional[dict]
    pdf: Optional[bytes]
    docx: Optional[bytes]
    ats_pdf: Optional[bytes]
    ats_docx: Optional[bytes]
    export_report: Optional[dict]
    progress: list
    errors: list
    cancelled: bool
