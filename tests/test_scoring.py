from src.agents.drafting import build_document
from src.agents.job_analysis import analyse_rules
from src.agents.matching import match_rules
from src.agents.validation import validate_profile
from src.config import READINESS_NOTE
from src.models.job import RequirementMatch
from src.models.profile import CandidateProfile, Experience
from src.scoring.readiness import assess, score_relevance
from src.templates.registry import RenderOptions, get_template


def _score(p, tid="classic_ats", jd=True, **kw):
    ja = analyse_rules(p.target.job_description) if jd and p.target.job_description else None
    matches = match_rules(ja, p) if ja else []
    doc = build_document(p, ja, matches, get_template(tid), RenderOptions())
    return assess(p, doc, get_template(tid), matches, ja, validate_profile(p).model_dump(), [], **kw)


def test_relevance_unavailable_without_job_description(gis_profile):
    rep = _score(gis_profile)
    rel = next(c for c in rep.components if c.key == "relevance")
    assert not rel.available and rel.points is None
    assert rep.max_available == 25 + 20 + 15          # layout also unavailable before rendering
    assert rep.note == READINESS_NOTE


def test_total_is_sum_of_components_and_deductions_explained(gis_profile, gis_job):
    gis_profile.target.job_description = gis_job
    rep = _score(gis_profile)
    avail = [c for c in rep.components if c.available]
    assert abs(rep.total - sum(c.points for c in avail)) < 0.01
    for c in avail:
        assert abs(c.points - max(0, c.max_points - sum(d.points for d in c.deductions))) < 0.05
        assert all(d.reason and d.fix for d in c.deductions)


def test_weak_profile_scores_low_even_when_generated_by_app():
    p = CandidateProfile(full_name="Test Person", experience=[Experience(title="Helper", employer="Shop", bullets=[
        "responsible for helping", "I did tasks", "worked on stuff", "helped"])])
    p.contact.email = "t@example.com"
    rep = _score(p)
    assert rep.percent < 75
    clarity = next(c for c in rep.components if c.key == "clarity")
    assert clarity.points < 12


def test_presentation_template_loses_parsing_points(gis_profile):
    ats = next(c for c in _score(gis_profile, "classic_ats").components if c.key == "parsing")
    pres = next(c for c in _score(gis_profile, "creative_portfolio").components if c.key == "parsing")
    assert pres.points < ats.points


def test_relevance_weights_required_over_preferred():
    def m(i, st, imp, s):
        return RequirementMatch(requirement_id=i, requirement=i, status=st, importance=imp, strength=s)
    from src.models.job import JobAnalysis, JobRequirement
    ja = JobAnalysis(requirements=[JobRequirement(id="a", text="a")])
    miss_req = score_relevance([m("a", "not_demonstrated", "required", 0), m("b", "supported", "preferred", 1)], ja, "jd")
    miss_pref = score_relevance([m("a", "supported", "required", 1), m("b", "not_demonstrated", "preferred", 0)], ja, "jd")
    assert miss_pref.points > miss_req.points
    assert miss_req.points == 10.0 and miss_pref.points == 20.0


def test_llm_estimates_are_labelled():
    from src.models.job import JobAnalysis, JobRequirement
    ja = JobAnalysis(requirements=[JobRequirement(id="a", text="a")])
    rm = RequirementMatch(requirement_id="a", requirement="a", status="supported", strength=1, method="llm-estimate")
    comp = score_relevance([rm], ja, "jd")
    assert comp.estimate and "estimate" in comp.note.lower()


def test_layout_component_uses_render_and_export(gis_profile):
    good = _score(gis_profile, render={"pages": 1, "body_size": 10.5, "density": 0},
                  export={"pdf": {"blank_pages": [], "clipped": False}}, max_pages=1)
    over = _score(gis_profile, render={"pages": 3, "body_size": 10.0, "density": 3},
                  export={"pdf": {"blank_pages": [3], "clipped": True}}, max_pages=1)
    g = next(c for c in good.components if c.key == "layout")
    o = next(c for c in over.components if c.key == "layout")
    assert g.points == 10 and o.points <= 2 and good.final
