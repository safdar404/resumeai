from src.agents.drafting import build_document
from src.agents.factual_review import review
from src.agents.job_analysis import analyse_rules
from src.agents.matching import match_rules
from src.config import EXAMPLES_DIR
from src.models.job import JobAnalysis, JobRequirement
from src.templates.registry import RenderOptions, get_template


def test_gis_job_matches_supported_evidence(gis_profile, gis_job):
    ja = analyse_rules(gis_job)
    assert ja.sector == "gis"
    assert any(r.importance == "preferred" for r in ja.requirements)
    ms = {m.requirement[:20]: m for m in match_rules(ja, gis_profile)}
    statuses = [m.status for m in ms.values()]
    assert statuses.count("supported") >= 5
    lidar = next(m for m in ms.values() if "LiDAR" in m.requirement)
    assert lidar.status == "not_demonstrated" and not lidar.evidence


def test_unrelated_job_has_no_false_support(gis_profile):
    ja = analyse_rules((EXAMPLES_DIR / "job_staff_nurse.txt").read_text())
    assert all(m.status == "not_demonstrated" for m in match_rules(ja, gis_profile))


def test_transferable_via_skill_family(gis_profile):
    ja = JobAnalysis(requirements=[JobRequirement(id="r1", text="Experience with MySQL", keywords=["mysql"])])
    m = match_rules(ja, gis_profile)[0]
    assert m.status == "transferable"     # PostGIS/SQL are related, MySQL itself is not claimed


def test_years_requirement_uses_dates(gis_profile):
    ja = JobAnalysis(requirements=[JobRequirement(id="r1", text="15+ years of experience", category="experience", years=15)])
    assert match_rules(ja, gis_profile)[0].status == "not_demonstrated"


def test_unsupported_keywords_not_inserted_into_resume(gis_profile, gis_job):
    ja = analyse_rules(gis_job)
    doc = build_document(gis_profile, ja, match_rules(ja, gis_profile), get_template("gis_geoai"), RenderOptions())
    text = doc.plain_text().lower()
    for kw in ("lidar", "openlayers", "leaflet", "azure", "aws"):
        assert kw not in text


def _doc(gis_profile):
    return build_document(gis_profile, None, [], get_template("classic_ats"), RenderOptions())


def test_review_reverts_invented_numbers_tools_and_names(gis_profile):
    doc = _doc(gis_profile)
    exp = doc.section("experience")
    original = exp.entries[0].bullets[1]
    exp.entries[0].bullets[1] = "Produced 75 county maps with LiDAR for Microsoft, cutting costs 30%"
    doc.section("summary").text = "GIS lead with 15+ years of experience in AWS and Kubernetes."
    doc2, rep = review(doc, gis_profile)
    assert rep.reverted >= 2
    assert doc2.section("experience").entries[0].bullets[1] == original
    assert "15+" not in doc2.section("summary").text and "AWS" not in doc2.section("summary").text


def test_review_restores_tampered_identity(gis_profile):
    doc = _doc(gis_profile)
    doc.name = "Someone Else"
    doc.section("experience").entries[0].subheading = "Fake Corp"
    doc2, rep = review(doc, gis_profile)
    assert doc2.name == gis_profile.full_name
    assert doc2.section("experience").entries[0].subheading == gis_profile.experience[0].employer


def test_user_edits_are_flagged_not_reverted(gis_profile):
    doc = _doc(gis_profile)
    e = doc.section("experience").entries[0]
    e.bullets[0] = "Led a team of 12 analysts"
    doc.user_edited_paths = [e.bullet_sources[0]]
    doc2, rep = review(doc, gis_profile)
    assert doc2.section("experience").entries[0].bullets[0] == "Led a team of 12 analysts"
    assert not rep.passed and rep.findings[0].action == "flagged"


def test_clean_draft_passes(gis_profile):
    _, rep = review(_doc(gis_profile), gis_profile)
    assert rep.passed and rep.reverted == 0
