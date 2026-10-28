"""Per-session workflow runner.

Each browser session owns its own compiled graph, in-memory checkpointer and
random thread id, so one visitor's state is never reachable from another's.
The checkpointer keeps a paused run (clarification interrupt) alive across
Streamlit reruns; completed runs are deleted to keep memory bounded.

Hosted note: InMemorySaver lives in the server process. On Streamlit
Community Cloud, state is lost when the app restarts or the session ends —
by design, as candidate data is not retained. For durable multi-instance
persistence use a database checkpointer (e.g. langgraph-checkpoint-postgres)
with encryption and a retention policy.
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.graph.builder import build_graph

RESULT_KEYS = ("profile", "validation", "corrections", "checked_fields", "assistant_message", "next_field",
               "asked_counts", "unverified", "job_analysis", "matches", "draft", "review", "score", "layout",
               "render_info", "pdf", "docx", "ats_pdf", "ats_docx", "export_report", "progress", "errors", "cancelled")


class WorkflowRunner:
    def __init__(self) -> None:
        self.thread_id = uuid.uuid4().hex
        self.saver = InMemorySaver()
        self.graph = build_graph(self.saver)

    def _config(self, llm) -> dict:
        return {"configurable": {"thread_id": self.thread_id, "llm": llm}, "recursion_limit": 60}

    def pending_interrupt(self) -> dict | None:
        snap = self.graph.get_state({"configurable": {"thread_id": self.thread_id}})
        if snap and snap.next and snap.interrupts:
            return snap.interrupts[0].value
        return None

    def _finish(self, result: dict) -> dict[str, Any]:
        out = {k: result[k] for k in RESULT_KEYS if k in result}
        intr = result.get("__interrupt__")
        out["interrupt"] = intr[0].value if intr else None
        if not intr:
            self.saver.delete_thread(self.thread_id)
        return out

    def run(self, inputs: dict, llm=None) -> dict[str, Any]:
        if self.pending_interrupt() is not None:
            self.saver.delete_thread(self.thread_id)  # abandon an unanswered pause
        return self._finish(self.graph.invoke(inputs, self._config(llm)))

    def resume(self, answers: dict, llm=None) -> dict[str, Any]:
        return self._finish(self.graph.invoke(Command(resume=answers), self._config(llm)))

    def reset(self) -> None:
        self.saver.delete_thread(self.thread_id)
        self.thread_id = uuid.uuid4().hex
