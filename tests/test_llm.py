from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

import src.services.llm as llm_mod
from src.agents.intake import intake_document
from src.agents.job_analysis import analyse_job
from src.agents.matching import match_evidence
from src.models.job import JobAnalysis, JobRequirement
from src.models.profile import CandidateProfile
from src.security.credentials import check_api_key, mask
from src.services.llm import LLMError, LLMService, LLMSettings, build_service
from tests.fakes import AuthenticationError, FakeChatModel, RateLimitError

PROMPT = ChatPromptTemplate.from_messages([("human", "x{format_feedback}")])


class Out(BaseModel):
    value: int


def _svc(responses, provider="openai"):
    return LLMService(LLMSettings(provider=provider, api_key="sk-test-0123456789abcdef"), chat_model=FakeChatModel(responses))


def test_malformed_then_valid_is_retried_once(monkeypatch):
    svc = _svc([{"wrong": 1}, {"value": 3}])
    assert svc.structured(Out, PROMPT, {}).value == 3


def test_persistently_malformed_raises_classified_error():
    svc = _svc([{"wrong": 1}, None, None])
    try:
        svc.structured(Out, PROMPT, {})
        raise AssertionError("expected LLMError")
    except LLMError as e:
        assert e.kind == "malformed"


def test_rate_limit_retries_are_bounded(monkeypatch):
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    svc = _svc([RateLimitError("429")] * 5)
    try:
        svc.structured(Out, PROMPT, {})
    except LLMError as e:
        assert e.kind == "rate_limit"
    assert svc._model.calls == 1 + llm_mod.LLM_MAX_TRANSIENT_RETRIES


def test_auth_error_not_retried():
    svc = _svc([AuthenticationError("401"), {"value": 1}])
    try:
        svc.structured(Out, PROMPT, {})
    except LLMError as e:
        assert e.kind == "auth" and "rejected" in e.user_message()
    assert svc._model.calls == 1


def test_node_falls_back_to_rules_on_llm_failure(gis_job):
    svc = _svc([{"requirements": "not a list"}, "not even a dict"])
    ja, errs = analyse_job(gis_job, "GIS Analyst", svc)
    assert ja.method == "rules" and ja.requirements and errs


def test_llm_cannot_claim_support_without_valid_evidence(gis_profile):
    ja = JobAnalysis(requirements=[JobRequirement(id="r1", text="Kubernetes administration", keywords=["kubernetes"])])
    fake = {"matches": [{"requirement_id": "r1", "status": "supported", "evidence_ids": ["made_up_id"]}]}
    matches, errs = match_evidence(ja, gis_profile, _svc([fake]))
    assert matches[0].status != "supported"


def test_llm_import_flags_values_not_in_document():
    text = "Jane Example\njane@example.com\nEXPERIENCE\nAnalyst | Contoso\n2020 - 2022\n- Built maps"
    extracted = CandidateProfile(full_name="Jane Example", experience=[
        {"title": "Analyst", "employer": "Contoso", "start_date": "2020", "end_date": "2022",
         "bullets": ["Built maps", "Increased revenue by 300%"]}])
    p, unverified, errs, method = intake_document(CandidateProfile(), text, _svc([extracted]))
    assert method == "llm"
    assert "experience[0].bullets[1]" in unverified and "experience[0].bullets[0]" not in unverified


def test_credentials_checked_without_modification():
    for bad, frag in [(" sk-abcdefghijklmnop", "whitespace"), ("sk-abc defghijklmnop", "inside"),
                      ("sk-abcdefghijklmnop\n", "whitespace"), ("sk-abcdefghijklmnop\u200b", "non-ASCII"),
                      ('"sk-abcdefghijklmnop"', "quotation"), ("abc12", "short"), ("", "No API key")]:
        chk = check_api_key(bad)
        assert not chk.ok and any(frag in p for p in chk.problems), bad
        assert all(bad.strip() not in p for p in chk.problems if bad.strip())   # never echoed
    assert check_api_key("sk-abcdefghijklmnop1234").ok
    assert "sk-" not in mask("sk-abcdefghijklmnop1234")


def test_invalid_key_format_is_reported_not_hidden():
    svc, err = build_service(LLMSettings(provider="openai", api_key=" sk-abcdefghijklmnop"))
    assert svc is None and "whitespace" in err
    svc, err = build_service(LLMSettings(provider="anthropic", api_key=None))
    assert svc is None and "No API key" in err
    assert build_service(LLMSettings(provider="none")) == (None, None)


def test_empty_llm_analysis_is_reported_not_silent(gis_job):
    ja, errs = analyse_job(gis_job, "GIS Analyst", _svc([{"title": "x", "requirements": []}]))
    assert ja.method == "rules" and ja.requirements and errs
