import pytest
from langchain_core.messages import AIMessage, ToolMessage
from src.agents.tool_agent import run_tool_loop, MAX_CALLS
from src.services.llm import LLMError


class FakeToolsModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.histories = []
    def bind_tools(self, tools):
        assert {'get_profile', 'update_profile', 'generate_resume'} <= {t['function']['name'] for t in tools}
        return self
    def invoke(self, messages):
        self.histories.append(list(messages))
        response = next(self.replies)
        if isinstance(response, Exception):
            raise response
        return response


def call(name, args, ident):
    return {'name': name, 'args': args, 'id': ident, 'type': 'tool_call'}


def test_native_profile_update_then_generate_tool_protocol():
    model = FakeToolsModel([
        AIMessage(content='', tool_calls=[call('update_profile', {'profile': {'full_name': 'Ali Hassan'}}, '1')]),
        AIMessage(content='', tool_calls=[call('generate_resume', {}, '2')]),
        AIMessage(content='Your PDF and Word files are ready.'),
    ])
    seen = []
    def execute(name, args):
        seen.append((name, args))
        return {'ok': True, 'message': 'Generated actual files.'} if name == 'generate_resume' else {'ok': True}
    result = run_tool_loop(model, [{'role': 'user', 'content': 'I am Ali Hassan. Generate my resume.'}], {}, execute)
    assert [x[0] for x in seen] == ['update_profile', 'generate_resume']
    assert seen[0][1]['profile']['full_name'] == 'Ali Hassan'
    tools = [m for m in model.histories[-1] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tools] == ['1', '2']
    assert 'Generated actual files.' in result


def test_unknown_tool_is_not_executed():
    model = FakeToolsModel([AIMessage(content='', tool_calls=[call('delete_profile', {}, 'x')]), AIMessage(content='Please provide your role.')])
    def execute(*args):
        raise AssertionError('Unknown tool must not execute')
    result = run_tool_loop(model, [], {}, execute)
    assert 'role' in result
    assert 'Unknown tool' in model.histories[-1][-1].content


def test_tool_loop_is_bounded():
    model = FakeToolsModel([AIMessage(content='', tool_calls=[call('get_profile', {}, str(i))]) for i in range(3)])
    n = []
    result = run_tool_loop(model, [], {}, lambda *args: n.append(1) or {'ok': True}, max_rounds=3)
    assert len(n) == 3 and 'limit' in result


def test_raw_exception_text_is_not_returned_to_model():
    model = FakeToolsModel([AIMessage(content='', tool_calls=[call('get_profile', {}, 'x')]), AIMessage(content='Try again.')])
    def execute(*args):
        raise ValueError('PRIVATE PROFILE CONTENT')
    run_tool_loop(model, [], {}, execute)
    assert 'PRIVATE' not in model.histories[-1][-1].content


def test_provider_error_does_not_destroy_facts():
    context = {'full_name': 'Ali Hassan'}
    model = FakeToolsModel([RuntimeError('sensitive')])
    with pytest.raises(LLMError):
        run_tool_loop(model, [], context, lambda *args: {})
    assert context == {'full_name': 'Ali Hassan'}


def test_groq_and_gemini_config_aliases(monkeypatch):
    from src.config import provider_defaults
    monkeypatch.setenv('RESUME_LLM_PROVIDER', 'groq')
    monkeypatch.delenv('LLM_PROVIDER', raising=False)
    assert provider_defaults().provider == 'groq'
    assert provider_defaults().base_url == 'https://api.groq.com/openai/v1'
    monkeypatch.setenv('RESUME_LLM_PROVIDER', 'gemini')
    assert provider_defaults().provider == 'gemini'
    assert 'generativelanguage.googleapis.com' in provider_defaults().base_url


def test_tool_agent_preserves_native_profile_and_existing_lists(monkeypatch):
    from types import SimpleNamespace
    import streamlit as st
    from src.models.profile import CandidateProfile, Experience
    from src.agents.tool_agent import run_resume_agent
    from src.ui import state as S
    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__
    profile = CandidateProfile(full_name='Ali Hassan', experience=[Experience(title='Analyst', employer='Example Ltd')])
    state = State(profile=profile, profile_version=0, chat=[{'role':'user','content':'My technical skill is Python.'}],
                  template_id='classic_ats', results=None, results_stale=True, validation={})
    monkeypatch.setattr(st, 'session_state', state)
    monkeypatch.setattr(S, 'refresh_checks', lambda: None)
    model = FakeToolsModel([AIMessage(content='', tool_calls=[call('update_profile', {'profile':{'skills':{'technical':['Python']}}}, 'x')]), AIMessage(content='Saved your Python skill.')])
    run_resume_agent('My technical skill is Python.', SimpleNamespace(_model=model))
    assert isinstance(state.profile, CandidateProfile)
    assert state.profile.full_name == 'Ali Hassan'
    assert state.profile.experience[0].employer == 'Example Ltd'
    assert state.profile.skills.technical == ['Python']


def test_tool_agent_rejects_unsupplied_metrics(monkeypatch):
    from types import SimpleNamespace
    import streamlit as st
    from src.models.profile import CandidateProfile
    from src.agents.tool_agent import run_resume_agent
    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__
    state = State(profile=CandidateProfile(full_name='Ali Hassan'), chat=[{'role':'user','content':'I used Python.'}], template_id='classic_ats')
    monkeypatch.setattr(st, 'session_state', state)
    model = FakeToolsModel([AIMessage(content='', tool_calls=[call('update_profile', {'profile':{'experience':[{'title':'Developer','employer':'Example','bullets':['Saved 500000 dollars.']}]}}, 'x')]), AIMessage(content='Please confirm the employer and results.')])
    run_resume_agent('I used Python.', SimpleNamespace(_model=model))
    assert state.profile.experience == []
    assert 'needs_confirmation' in model.histories[-1][-1].content
