from src.graph.runner import WorkflowRunner
from src.models.profile import CandidateProfile


def _gen(runner, profile, **extra):
    inputs = {"mode": "generate", "profile": profile.model_dump(), "template_id": "classic_ats",
              "options": {"page_target": "1"}}
    inputs.update(extra)
    return runner.run(inputs)


def test_full_generation_produces_validated_files(gis_profile, gis_job):
    gis_profile.target.job_description = gis_job
    res = _gen(WorkflowRunner(), gis_profile)
    assert res["interrupt"] is None
    assert res["pdf"][:4] == b"%PDF" and res["docx"][:2] == b"PK"
    assert res["export_report"]["pdf"]["text_extractable"]
    assert res["score"]["final"] and res["score"]["max_available"] == 100
    assert any("Matched evidence" in m for m in res["progress"])
    assert any("Re-opened" in m for m in res["progress"])


def test_missing_name_interrupts_then_resumes(gis_profile):
    gis_profile.full_name = ""
    r = WorkflowRunner()
    res = _gen(r, gis_profile)
    assert res["interrupt"] and not res.get("pdf")
    paths = [q["path"] for i in res["interrupt"]["issues"] for q in i["questions"]]
    assert "full_name" in paths
    assert r.pending_interrupt() is not None          # paused state survives in checkpointer
    res2 = r.resume({"full_name": "Amara Okafor-Lindqvist"})
    assert res2["interrupt"] is None and res2["pdf"]
    assert res2["profile"]["full_name"] == "Amara Okafor-Lindqvist"
    assert r.pending_interrupt() is None


def test_cancel_clarification_ends_without_files(gis_profile):
    gis_profile.contact.email = "broken@"
    r = WorkflowRunner()
    assert _gen(r, gis_profile)["interrupt"]
    res = r.resume({"__cancel__": True})
    assert res["cancelled"] and not res.get("pdf")


def test_session_isolation(gis_profile):
    a, b = WorkflowRunner(), WorkflowRunner()
    assert a.thread_id != b.thread_id and a.saver is not b.saver
    gis_profile.full_name = ""
    _gen(a, gis_profile)                               # a is paused with a's data
    assert a.pending_interrupt() is not None
    assert b.pending_interrupt() is None
    other = CandidateProfile.model_validate(gis_profile.model_dump())
    other.full_name = "Different Person"
    res_b = _gen(b, other)
    assert "Amara" not in str(res_b["profile"]["full_name"])
    assert b.graph.get_state({"configurable": {"thread_id": a.thread_id}}).values == {}


def test_completed_runs_are_not_retained(gis_profile):
    r = WorkflowRunner()
    _gen(r, gis_profile)
    assert r.graph.get_state({"configurable": {"thread_id": r.thread_id}}).values == {}


def test_offline_chat_intake_asks_next_question_and_never_repeats():
    r = WorkflowRunner()
    p = CandidateProfile()
    asked = {"full_name": 1}
    res = r.run({"mode": "intake", "input_kind": "chat", "raw_input": "My name is Kofi Mensah-Lee",
                 "asked_field": "full_name", "asked_counts": asked, "profile": p.model_dump()})
    assert res["profile"]["full_name"] == "Kofi Mensah-Lee"
    assert res["next_field"] == "target"
    res2 = r.run({"mode": "intake", "input_kind": "chat", "raw_input": "skip", "asked_field": "target",
                  "asked_counts": res["asked_counts"], "profile": res["profile"]})
    assert "target" in res2["profile"]["skipped_fields"]
    assert res2["next_field"] != "target" and res2["next_field"] != "full_name"


def test_chat_extracts_contact_from_any_message():
    r = WorkflowRunner()
    res = r.run({"mode": "intake", "input_kind": "chat", "raw_input": "reach me at kofi@example.com or +233 20 000 0000",
                 "asked_field": "contact", "asked_counts": {"contact": 1}, "profile": CandidateProfile().model_dump()})
    assert res["profile"]["contact"]["email"] == "kofi@example.com"
    assert res["profile"]["contact"]["phone"].startswith("+233")


def test_rerender_flags_user_edit(gis_profile):
    r = WorkflowRunner()
    res = _gen(r, gis_profile)
    draft = res["draft"]
    entry = next(s for s in draft["sections"] if s["key"] == "experience")["entries"][0]
    entry["bullets"][0] = "Managed a 50-person team"
    draft["user_edited_paths"] = [entry["bullet_sources"][0]]
    res2 = r.run({"mode": "rerender", "profile": gis_profile.model_dump(), "template_id": "classic_ats",
                  "options": {"page_target": "1"}, "draft": draft, "job_analysis": res["job_analysis"],
                  "matches": res["matches"], "validation": res.get("validation")})
    assert res2["pdf"] and not res2["review"]["passed"]
    assert any(f["action"] == "flagged" for f in res2["review"]["findings"])


def test_generation_error_is_safe_and_identifies_stage(gis_profile, monkeypatch):
    import pytest
    from src.graph.runner import WorkflowError
    from src.graph import nodes

    def fail(state):
        raise ValueError('PRIVATE RESUME CONTENT MUST NOT BE SHOWN')

    monkeypatch.setattr(nodes, 'document_rendering', fail)
    runner = WorkflowRunner()
    with pytest.raises(WorkflowError) as err:
        _gen(runner, gis_profile)
    assert 'document rendering (ValueError)' in str(err.value)
    assert 'PRIVATE' not in str(err.value)
