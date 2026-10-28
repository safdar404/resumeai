"""Headless UI tests with Streamlit's AppTest (no browser needed)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.state import STEPS


def _app():
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=180)
    at.run()
    return at


def _goto(at, i):
    at.session_state["step"] = i
    at.session_state["nav_radio"] = STEPS[i]
    at.run()


def _no_errors(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not [e for e in at.error if "went wrong" in e.value]


def test_every_step_renders_empty():
    at = _app()
    for i in range(len(STEPS)):
        _goto(at, i)
        _no_errors(at)


def test_sample_flow_generate_edit_download():
    at = _app()
    next(b for b in at.button if b.label.startswith("Load a fictional")).click().run()
    _no_errors(at)
    assert at.session_state["profile"].full_name == "Amara Okafor-Lindqvist"
    assert any(c["status"] == "applied" for c in at.session_state["corrections"])
    _goto(at, 5)
    next(b for b in at.button if b.label.startswith("Generate")).click().run()
    _no_errors(at)
    res = at.session_state["results"]
    assert res["pdf"] and res["score"]["final"]
    for i in (6, 7, 8):
        _goto(at, i)
        _no_errors(at)
    assert len(at.get("download_button")) >= 3


def test_chat_turn_updates_profile():
    at = _app()
    _goto(at, 1)
    at.chat_input[0].set_value("Kofi Mensah-Lee").run()
    _no_errors(at)
    assert at.session_state["profile"].full_name == "Kofi Mensah-Lee"
    assert at.session_state["chat"][-1]["role"] == "assistant"


def test_two_sessions_are_isolated():
    a, b = _app(), _app()
    next(x for x in a.button if x.label.startswith("Load a fictional")).click().run()
    assert a.session_state["profile"].full_name and not b.session_state["profile"].full_name
    assert a.session_state["session_id"] != b.session_state["session_id"]
    assert a.session_state["runner"].thread_id != b.session_state["runner"].thread_id


def test_clear_session_wipes_data():
    at = _app()
    next(x for x in at.button if x.label.startswith("Load a fictional")).click().run()
    old = at.session_state["session_id"]
    next(x for x in at.button if "Clear my session" in x.label).click().run()
    assert at.session_state["session_id"] != old
    assert not at.session_state["profile"].full_name and at.session_state["results"] is None


def test_corrected_date_resumes_generation_after_profile_edit():
    at = _app()
    next(b for b in at.button if b.label.startswith('Load a fictional')).click().run()
    p = at.session_state['profile'].model_copy(deep=True)
    p.education[0].start_date = 'unrecognised date'
    at.session_state['profile'] = p
    _goto(at, 5)
    next(b for b in at.button if b.label.startswith('Generate')).click().run()
    _no_errors(at)
    assert at.session_state['interrupt']
    # Intake triggered by profile edits abandons the old workflow checkpoint.
    at.session_state['runner'].reset()
    next(t for t in at.text_input if t.label == 'Start date').set_value('2009')
    next(t for t in at.text_input if t.label == 'End / expected date').set_value('2011')
    next(b for b in at.button if b.label == 'Submit answers and continue').click().run()
    _no_errors(at)
    assert at.session_state['results']['pdf'].startswith(b'%PDF')
    assert at.session_state['profile'].education[0].start_date == '2009'


def test_copilot_selects_template_and_generates_resume():
    at = _app()
    next(b for b in at.button if b.label.startswith('Load a fictional')).click().run()
    next(b for b in at.button if b.label == '✦ Open resume copilot').click().run()
    at.chat_input[0].set_value('use GIS & GeoAI Professional template').run()
    _no_errors(at)
    assert at.session_state['template_id'] == 'gis_geoai'
    at.chat_input[0].set_value('generate my resume').run()
    _no_errors(at)
    assert at.session_state['results']['render_info']['template_id'] == 'gis_geoai'
    assert at.session_state['results']['pdf'].startswith(b'%PDF')


def test_template_selection_marks_exports_outdated():
    at = _app()
    next(b for b in at.button if b.label.startswith('Load a fictional')).click().run()
    _goto(at, 5)
    next(b for b in at.button if b.label.startswith('Generate')).click().run()
    _goto(at, 4)
    at.button(key='sel_modern_professional').click().run()
    _no_errors(at)
    assert at.session_state['results_stale']
    _goto(at, 8)
    assert not any(b.label == '⬇ Download PDF' for b in at.get('download_button'))


def test_back_navigation_on_every_relevant_step():
    at = _app()
    for step in range(1, len(STEPS)):
        _goto(at, step)
        _no_errors(at)
        button = at.button(key=f'top_back_{step}')
        assert button.label.startswith('← Back to ')
        button.click().run()
        assert at.session_state['step'] == step - 1


def test_blocked_generate_opens_experience_form_directly():
    at = _app()
    _goto(at, 5)
    next(b for b in at.button if b.label.startswith('Generate')).click().run()
    # Empty profile also needs contact/name; structural actions must still work.
    assert any(b.label == '＋ Add experience' for b in at.button)
    next(b for b in at.button if b.label == '＋ Add experience').click().run()
    _no_errors(at)
    assert at.session_state['step'] == 1
    assert at.session_state['entry_mode'] == 'Form'
    assert at.session_state['profile_form_tab'] == 'Experience'
    assert len(at.session_state['profile'].experience) == 1
    assert at.session_state['interrupt'] is None
    assert any(b.label == 'Save role' for b in at.button)
    assert any(b.label == 'Return to Generate →' for b in at.button)


def test_action_only_block_has_navigation_and_no_disabled_submit():
    at = _app()
    p = at.session_state['profile'].model_copy(deep=True)
    p.full_name = 'Example Person'; p.contact.email = 'example@example.com'
    at.session_state['profile'] = p
    _goto(at, 5)
    next(b for b in at.button if b.label.startswith('Generate')).click().run()
    _no_errors(at)
    assert any(b.label == '＋ Add education' for b in at.button)
    assert not any(b.label == 'Submit answers and continue' for b in at.button)
    at.button(key='top_back_5').click().run()
    assert at.session_state['step'] == 4
