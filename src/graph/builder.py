"""Compile the CareerRainbow LangGraph workflow.

START → start → (intake | profile_validation | factual_review)
intake → profile_validation → language_correction → compose_reply → END            (mode=intake)
profile_validation → [clarification ⟲] → job_analysis → evidence_matching →
  resume_drafting ⇄ factual_review (bounded) → readiness_assessment →
  layout_planning → document_rendering → export_validation → END                   (mode=generate)
factual_review → readiness_assessment → … → export_validation → END                 (mode=rerender)
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph import nodes as n
from src.graph.state import ResumeState


def build_graph(checkpointer=None):
    g = StateGraph(ResumeState)
    g.add_node("start", n.start)
    g.add_node("intake", n.intake)
    g.add_node("profile_validation", n.profile_validation)
    g.add_node("language_correction", n.language_correction)
    g.add_node("compose_reply", n.compose_reply)
    g.add_node("clarification", n.clarification)
    g.add_node("job_analysis", n.job_analysis)
    g.add_node("evidence_matching", n.evidence_matching)
    g.add_node("resume_drafting", n.resume_drafting)
    g.add_node("factual_review", n.factual_review)
    g.add_node("readiness_assessment", n.readiness_assessment)
    g.add_node("layout_planning", n.layout_planning)
    g.add_node("document_rendering", n.document_rendering)
    g.add_node("export_validation", n.export_validation)

    g.add_edge(START, "start")
    g.add_conditional_edges("start", n.route_start, {"intake": "intake", "profile_validation": "profile_validation",
                                                     "factual_review": "factual_review"})
    g.add_edge("intake", "profile_validation")
    g.add_conditional_edges("profile_validation", n.route_after_validation,
                            {"language_correction": "language_correction", "clarification": "clarification",
                             "job_analysis": "job_analysis", "end": END})
    g.add_conditional_edges("language_correction", n.route_after_correction, {"compose_reply": "compose_reply", "end": END})
    g.add_edge("compose_reply", END)
    g.add_conditional_edges("clarification", n.route_after_clarification,
                            {"profile_validation": "profile_validation", "end": END})
    g.add_edge("job_analysis", "evidence_matching")
    g.add_edge("evidence_matching", "resume_drafting")
    g.add_edge("resume_drafting", "factual_review")
    g.add_conditional_edges("factual_review", n.route_after_review,
                            {"resume_drafting": "resume_drafting", "readiness_assessment": "readiness_assessment"})
    g.add_edge("readiness_assessment", "layout_planning")
    g.add_edge("layout_planning", "document_rendering")
    g.add_edge("document_rendering", "export_validation")
    g.add_edge("export_validation", END)
    return g.compile(checkpointer=checkpointer)
