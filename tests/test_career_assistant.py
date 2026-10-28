from src.agents.career_assistant import plan_action
from src.services.heuristic_parser import parse_resume_text
from src.agents.validation import validate_profile
from src.models.profile import Experience


def test_explicit_agent_actions_and_data_are_distinct():
    assert plan_action('generate my resume') == ('generate', None)
    assert plan_action('use GIS & GeoAI Professional template') == ('template', 'gis_geoai')
    assert plan_action('review my profile') == ('review', None)
    assert plan_action('I generated a resume application at my company')[0] == 'update'
    assert plan_action('Do not generate my resume')[0] == 'update'


def test_wrapped_role_import_keeps_responsibilities_out_of_location():
    text = '''Fictional Candidate
candidate@example.com
Professional Experience
GIS Specialist
Example Consulting, Lahore
5 February 2025 to 30 June 2026
• Developed geodatabases and
validated mapping datasets.
• Prepared maps for engineers.
GIS Analyst
Example Agency, Islamabad
1 March 2021 to 18 September 2023
• Supported cadastral mapping.
Professional Training and Credentials
GIS Certificate — Example Institute
Python and GeoAI Portfolio
Mapping Demo
• Developed a map.
Education
MSc GIS, Example University, 2009 - 2011
'''
    p = parse_resume_text(text)
    assert len(p.experience) == 2
    first = p.experience[0]
    assert first.location == 'Lahore'
    assert first.start_date == '5 February 2025'
    assert first.end_date == '30 June 2026'
    assert first.bullets == ['Developed geodatabases and validated mapping datasets.', 'Prepared maps for engineers.']
    assert p.certifications and p.projects


def test_contaminated_profile_is_blocked_before_export(gis_profile):
    gis_profile.experience[0].location = 'Responsibilities paragraph ' * 20
    gis_profile.skills.technical = ['Imported unrelated resume text ' * 15]
    report = validate_profile(gis_profile)
    paths = {i.path for i in report.blocking}
    assert 'experience[0].location' in paths and 'skills.technical' in paths
