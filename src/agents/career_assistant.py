"""Explicit user-intent tools for the career assistant.

The same per-session LangGraph performs validation, matching, drafting,
factual review and export. No external actions or invented career facts.
"""
from __future__ import annotations

import re
from src.templates.registry import TEMPLATES


def plan_action(message: str) -> tuple[str, str | None]:
    text = message.strip().lower()
    if re.search(r'^(?:/help|help|what can you do)[?.! ]*$', text):
        return 'help', None
    if text.startswith('/template ') or ('template' in text and re.search(r'\b(use|choose|select|switch)\b', text)):
        for template in sorted(TEMPLATES, key=lambda t: -len(t.name)):
            if template.id in text or template.name.lower() in text:
                return 'template', template.id
        return 'templates', None
    if text in ('/templates', 'show templates', 'show designs', 'browse templates'):
        return 'templates', None
    if text in ('/review', 'review my resume', 'review my profile', 'check my cv', 'check my resume'):
        return 'review', None
    if re.fullmatch(r'(?:/generate|(?:please )?(?:generate|build|create|regenerate)(?: my| the)? (?:cv|resume)(?: please)?)[.!]?', text):
        return 'generate', None
    if text in ('/preview', 'preview my resume', 'show my resume'):
        return 'preview', None
    return 'update', None


def handle_action(message: str) -> str | None:
    from src.ui import state as S
    import streamlit as st
    from src.agents.validation import validate_profile
    from src.graph.runner import WorkflowError
    from src.ui.steps.templates_step import _select

    action, tid = plan_action(message)
    if action == 'update':
        return None
    ss = st.session_state
    if action == 'help':
        return ('I can collect your experience, review imported sections, choose a design and run the resume workflow. '
                'Try **review my profile**, **use GIS & GeoAI Professional template**, '
                '**generate my resume**, or **preview my resume**.\n\n'
                'With an AI provider enabled in the sidebar, I also use it for extraction and drafting. '
                'Otherwise I use the offline rules engine. I never invent employers, dates or achievements.')
    if action == 'review':
        report = validate_profile(S.profile())
        ss.validation = report.model_dump()
        issues = report.issues
        if not issues:
            return 'Profile checks passed. Choose your design, then ask me to **generate my resume**.'
        return '**Profile review**\n\n' + '\n'.join('- ' + i.message for i in issues[:8]) + (
            '\n\nReview the affected fields in **Form** before generating. I will keep your original information.'
        )
    if action == 'template':
        _select(tid)
        name = next(t.name for t in TEMPLATES if t.id == tid)
        return f'**{name}** selected. Your previous export is marked out of date. Ask **generate my resume** to apply this design.'
    if action == 'templates':
        return '**Available designs**\n\n' + '\n'.join('- ' + t.name for t in TEMPLATES) + '\n\nSay **use Modern Professional template** to choose one, or open **Choose template** to compare previews.'
    if action == 'preview':
        if not ss.results:
            return 'No resume has been generated yet. Ask **generate my resume** when your profile is ready.'
        ss.agent_destination = 6
        return 'Opening your generated resume preview and editing workspace.'
    if action == 'generate':
        try:
            res = S.run_generate()
        except WorkflowError as exc:
            return str(exc)
        if res.get('interrupt'):
            ss.agent_destination = 5
            return 'I found details that need your confirmation. Opening the clarification form before drafting.'
        if res.get('pdf'):
            info = res.get('render_info') or {}
            return (f'Your resume is ready: **{info.get("pages", "?")} page(s)**. '
                    'The workflow validated your facts, checked job evidence, drafted, fact-checked and rendered PDF + Word files. '
                    'Use **Preview resume** below to inspect the result, or **Download files** to export it.')
        return 'Generation did not produce a file. Review the profile checks in Generate before trying again.'
    return None
