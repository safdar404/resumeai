from src.agents import correction as C
from src.models.profile import CandidateProfile, Experience
from src.services.correction import correct_text, facts_preserved, run_rule_corrections


def test_spec_examples():
    out, notes, cats = correct_text("mange GIS databse", protected=set(), is_bullet=True, past_role=True)
    assert out == "Managed GIS database"
    assert "tense" in cats and "spelling" in cats
    out, *_ = correct_text("Pythn programing", protected=set(), is_bullet=True)
    assert out == "Python programming"


def test_numbers_units_and_urls_preserved():
    src = "built 3  dashboards for 1,200 users at https://exmaple-databse.com , saving 15%"
    out, *_ = correct_text(src, protected=set(), is_bullet=True)
    assert "1,200" in out and "15%" in out and "https://exmaple-databse.com" in out
    assert facts_preserved(src, out, set())[0]


def test_protected_names_never_changed():
    p = CandidateProfile(full_name="Mange Okoro", experience=[Experience(
        title="Analyst", employer="Databse Labs", start_date="2019", end_date="2020",
        bullets=["worked with Databse Labs clients and Mange Okoro on recieve logs"])])
    out, *_ = correct_text(p.experience[0].bullets[0], protected=p.protected_terms(), is_bullet=True, past_role=True)
    assert "Databse Labs" in out and "Mange Okoro" in out
    assert "receive" in out


def test_skill_name_changes_need_confirmation():
    p = CandidateProfile(full_name="A")
    p.skills.technical = ["pythn", "arcgis"]
    cs = run_rule_corrections(p)
    skill_cs = [c for c in cs if c.path.startswith("skills.")]
    assert skill_cs and all(c.requires_confirmation and c.status == "pending" for c in skill_cs)


def test_dictionary_guess_is_pending_not_applied():
    p = CandidateProfile(full_name="A", summary="Experienced analyst with strong comunicaton skills")
    cs = run_rule_corrections(p)
    sugg = [c for c in cs if "spelling_suggestion" in c.categories]
    assert sugg and all(c.status == "pending" for c in sugg)


def test_run_corrections_applies_routine_and_records(gis_profile):
    p2, cs, checked, errs = C.run_corrections(gis_profile, {}, set(), None)
    fixed = p2.experience[1].bullets[0]
    assert fixed.startswith("Managed GIS database")
    c = next(x for x in cs if x.path == "experience[1].bullets[0]")
    assert c.original == "mange GIS databse for utility network records in PostGIS"
    # unchanged text is not re-checked next time
    _, cs2, _, _ = C.run_corrections(p2, checked, set(), None)
    assert not [x for x in cs2 if x.status == "applied"]


def test_reject_restores_original_and_is_not_resuggested(gis_profile):
    p2, cs, checked, _ = C.run_corrections(gis_profile, {}, set(), None)
    c = next(x for x in cs if x.path == "experience[1].bullets[0]")
    p3, ok, _ = C.revert(p2, c)
    assert ok and p3.experience[1].bullets[0] == c.original
    checked[c.path] = c.original
    _, cs2, _, _ = C.run_corrections(p3, {}, {c.signature()}, None)
    assert c.signature() not in {x.signature() for x in cs2}


def test_revert_refuses_when_text_edited_after(gis_profile):
    p2, cs, _, _ = C.run_corrections(gis_profile, {}, set(), None)
    c = next(x for x in cs if x.path == "experience[1].bullets[0]")
    p2.experience[1].bullets[0] = "Something the user typed later"
    p3, ok, _ = C.revert(p2, c)
    assert not ok and p3.experience[1].bullets[0] == "Something the user typed later"


def test_facts_preserved_detects_changes():
    ok, why = facts_preserved("Mapped 40 counties in QGIS", "Mapped 45 counties in QGIS", {"qgis"})
    assert not ok and "numbers" in why
    ok, why = facts_preserved("Mapped counties in QGIS", "Mapped counties in ArcGIS", {"qgis"})
    assert not ok and "qgis" in why
