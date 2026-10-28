from src.agents.validation import apply_answers, validate_profile
from src.models.profile import CandidateProfile, Education, Experience


def _paths(rep, blocking=None):
    return {i.path for i in rep.issues if blocking is None or i.blocking == blocking}


def test_empty_profile_blocks_generation():
    rep = validate_profile(CandidateProfile())
    assert {"full_name", "contact.email", "experience"} <= _paths(rep, True)
    assert rep.completion < 20


def test_complete_sample_has_no_blocking_issues(gis_profile):
    rep = validate_profile(gis_profile)
    assert not rep.blocking
    assert rep.completion >= 85


def test_malformed_email_is_blocking(gis_profile):
    gis_profile.contact.email = "amara.example.com"
    rep = validate_profile(gis_profile)
    assert "contact.email" in _paths(rep, True)


def test_contradictory_dates_flagged_not_changed(gis_profile):
    gis_profile.experience[1].start_date = "2021"
    gis_profile.experience[1].end_date = "2019"
    rep = validate_profile(gis_profile)
    issue = next(i for i in rep.issues if i.path == "experience[1].start_date")
    assert issue.blocking and "ends before it starts" in issue.message
    assert gis_profile.experience[1].start_date == "2021"   # never silently altered


def test_current_role_with_end_date_flagged():
    p = CandidateProfile(full_name="A B", experience=[Experience(title="T", employer="E", start_date="2020",
                                                                  end_date="2022", current=True, bullets=["x"])])
    p.contact.email = "a@example.com"
    assert any("marked current" in i.message for i in validate_profile(p).issues)


def test_missing_institution_and_incomplete_links(gis_profile):
    gis_profile.education.append(Education(degree="Diploma"))
    gis_profile.contact.linkedin = "linkedin.com/in/"
    gis_profile.contact.github = "github.com"
    rep = validate_profile(gis_profile)
    assert "education[2].institution" in _paths(rep, True)
    assert "contact.linkedin" in _paths(rep, False)
    assert "contact.github" in _paths(rep, False)


def test_international_names_are_valid():
    for name in ["Zoë Łukasiewicz-Nguyễn", "Δημήτρης Παπαδόπουλος", "Иван Петров", "O'Connor-Ødegård", "李 明"]:
        p = CandidateProfile(full_name=name, education=[Education(degree="BSc", institution="Uni")])
        p.contact.email = "x@example.com"
        assert not validate_profile(p).blocking, name


def test_skipped_optional_fields_count_as_complete(gis_profile):
    gis_profile.summary = ""
    before = validate_profile(gis_profile).completion
    gis_profile.skipped_fields.append("summary")
    assert validate_profile(gis_profile).completion > before


def test_apply_answers_present_sets_current(gis_profile):
    p = apply_answers(gis_profile, {"experience[1].end_date": "Present", "full_name": "  Amara O.  "})
    assert p.experience[1].current is True and p.experience[1].end_date == ""
    assert p.full_name == "Amara O."


def test_referee_requires_permission(gis_profile):
    from src.models.profile import Referee
    gis_profile.include_referees = True
    gis_profile.referees = [Referee(name="Dr Example", permission_confirmed=False)]
    assert any("permission" in i.message for i in validate_profile(gis_profile).issues)
