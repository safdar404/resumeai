"""Fifteen resume designs, all rendered by the shared engine in
src/rendering. Each spec controls typography, spacing, hierarchy, section
order and restrained accents."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SECTION_TITLES = {
    "summary": "Professional Summary", "skills": "Skills", "experience": "Professional Experience",
    "projects": "Projects", "education": "Education", "certifications": "Certifications",
    "publications": "Publications", "languages": "Languages", "awards": "Awards",
    "volunteering": "Volunteering", "referees": "References",
}
ALL_SECTIONS = list(SECTION_TITLES)


class TemplateSpec(BaseModel):
    id: str
    name: str
    description: str
    recommended_for: list[str]
    layout: Literal["single", "sidebar"] = "single"
    presentation_oriented: bool = False
    font: str = "carlito"
    accent: str = "#1F2937"
    heading_style: Literal["rule", "caps_rule", "bar", "plain", "underline", "shaded", "spaced", "accent_text"] = "caps_rule"
    name_align: Literal["left", "center"] = "left"
    name_size: float = 20
    name_banner: bool = False
    date_style: Literal["right", "inline"] = "right"
    entry_order: Literal["title_first", "org_first"] = "title_first"
    bullet: str = "•"
    spacing: float = 1.0
    body_size: float = 10.5
    skills_style: Literal["inline", "grouped"] = "inline"
    section_order: list[str] = Field(default_factory=lambda: ["summary", "skills", "experience", "projects",
                                                               "education", "certifications", "publications",
                                                               "languages", "awards", "volunteering", "referees"])
    sidebar_sections: list[str] = Field(default_factory=list)
    page_options: list[str] = Field(default_factory=lambda: ["1", "2"])
    default_pages: str = "1"
    parsing_notes: str = ""
    section_titles: dict[str, str] = Field(default_factory=dict)

    def title_for(self, key: str) -> str:
        return self.section_titles.get(key, SECTION_TITLES[key])


_ATS = "Single column, standard headings, real text, contact details in the body — highly parsing-friendly."

TEMPLATES: list[TemplateSpec] = [
    TemplateSpec(id="classic_ats", name="Classic ATS",
                 description="Plain, conservative and maximally parseable. Small-caps style headings with a thin rule.",
                 recommended_for=["Any occupation", "Online application portals", "Government roles"],
                 font="liberation_sans", accent="#1F2937", heading_style="caps_rule", parsing_notes=_ATS),
    TemplateSpec(id="modern_professional", name="Modern Professional",
                 description="Two-column layout with a tinted sidebar for contact details, skills and languages.",
                 recommended_for=["Sales & marketing", "Business roles", "Networking / direct handover"],
                 layout="sidebar", presentation_oriented=True, font="carlito", accent="#0F766E",
                 heading_style="accent_text", sidebar_sections=["skills", "languages", "certifications"],
                 parsing_notes="Presentation-oriented: two columns can be read out of order by some ATS. "
                               "Use the parsing-friendly export for online portals."),
    TemplateSpec(id="compact_executive", name="Compact Executive",
                 description="Dense serif layout that fits leadership history; employer-first entries.",
                 recommended_for=["Directors", "Senior managers", "Board-level roles"], font="caladea",
                 accent="#1E3A5F", heading_style="spaced", name_align="center", entry_order="org_first",
                 spacing=0.85, default_pages="2",
                 section_order=["summary", "experience", "skills", "education", "certifications", "awards",
                                "projects", "publications", "languages", "volunteering", "referees"],
                 section_titles={"summary": "Executive Profile", "skills": "Core Competencies"},
                 parsing_notes=_ATS),
    TemplateSpec(id="graduate_starter", name="Graduate Starter",
                 description="Education and projects first, friendly sans-serif with clear underlined headings.",
                 recommended_for=["Fresh graduates", "Internships", "Students"], font="carlito",
                 accent="#2563EB", heading_style="underline", body_size=11,
                 section_order=["summary", "education", "projects", "skills", "experience", "certifications",
                                "awards", "volunteering", "languages", "publications", "referees"],
                 parsing_notes=_ATS),
    TemplateSpec(id="technical_engineer", name="Technical Engineer",
                 description="Skills grouped near the top, square bullets and a bold left accent bar on headings.",
                 recommended_for=["Software engineers", "Civil / structural engineers", "DevOps"],
                 font="liberation_sans", accent="#374151", heading_style="bar", bullet="▪", skills_style="grouped",
                 section_titles={"skills": "Technical Skills"}, parsing_notes=_ATS),
    TemplateSpec(id="ai_data", name="AI & Data Specialist",
                 description="Violet accent rule, skills and projects prominent for portfolios of models and analyses.",
                 recommended_for=["Data scientists", "ML engineers", "BI analysts"], font="carlito",
                 accent="#6D28D9", heading_style="rule", skills_style="grouped", bullet="›",
                 section_order=["summary", "skills", "experience", "projects", "publications", "education",
                                "certifications", "awards", "languages", "volunteering", "referees"],
                 section_titles={"skills": "Technical Toolkit"}, parsing_notes=_ATS),
    TemplateSpec(id="gis_geoai", name="GIS & GeoAI Professional",
                 description="Earth-green accent bar, geospatial toolkit up front, projects for mapping work.",
                 recommended_for=["GIS analysts", "Remote sensing", "GeoAI", "Surveying"], font="liberation_sans",
                 accent="#047857", heading_style="bar", skills_style="grouped",
                 section_order=["summary", "skills", "experience", "projects", "education", "certifications",
                                "publications", "awards", "languages", "volunteering", "referees"],
                 section_titles={"skills": "Geospatial & Technical Skills"}, parsing_notes=_ATS),
    TemplateSpec(id="project_manager", name="Project Manager",
                 description="Warm amber rules, certifications (PMP, PRINCE2) raised near the top.",
                 recommended_for=["Project / programme managers", "PMO", "Construction management"],
                 font="carlito", accent="#B45309", heading_style="caps_rule",
                 section_order=["summary", "certifications", "experience", "skills", "education", "projects",
                                "awards", "languages", "volunteering", "publications", "referees"],
                 section_titles={"skills": "Key Competencies"}, parsing_notes=_ATS),
    TemplateSpec(id="finance", name="Finance Professional",
                 description="Traditional serif, centred name, navy rules; qualifications emphasised.",
                 recommended_for=["Accountants", "Auditors", "Financial analysts"], font="liberation_serif",
                 accent="#1E3A8A", heading_style="caps_rule", name_align="center",
                 section_order=["summary", "experience", "certifications", "education", "skills", "awards",
                                "languages", "projects", "volunteering", "publications", "referees"],
                 section_titles={"certifications": "Professional Qualifications"}, parsing_notes=_ATS),
    TemplateSpec(id="healthcare", name="Healthcare Professional",
                 description="Calm teal headings with licences and certifications before experience.",
                 recommended_for=["Nurses", "Allied health", "Clinical staff"], font="carlito", accent="#0E7490",
                 heading_style="underline", body_size=11,
                 section_order=["summary", "certifications", "experience", "education", "skills", "languages",
                                "volunteering", "awards", "projects", "publications", "referees"],
                 section_titles={"certifications": "Licences & Certifications", "skills": "Clinical Skills"},
                 parsing_notes=_ATS),
    TemplateSpec(id="academic_research", name="Academic & Research",
                 description="Long-form CV in serif type: education, research and publications first.",
                 recommended_for=["Researchers", "Lecturers", "PhD applicants"], font="dejavu_serif",
                 accent="#4B5563", heading_style="plain", date_style="inline", page_options=["2", "academic"],
                 default_pages="academic",
                 section_order=["summary", "education", "experience", "publications", "projects", "awards",
                                "certifications", "skills", "languages", "volunteering", "referees"],
                 section_titles={"summary": "Research Profile", "experience": "Academic & Professional Appointments",
                                 "projects": "Research Projects", "awards": "Grants & Awards"},
                 parsing_notes=_ATS + " Academic length is expected; page limits are relaxed."),
    TemplateSpec(id="career_transition", name="Career Transition",
                 description="Leads with transferable skills and projects before the employment history.",
                 recommended_for=["Career changers", "Returners", "Bootcamp graduates"], font="carlito",
                 accent="#BE185D", heading_style="rule",
                 section_order=["summary", "skills", "projects", "experience", "education", "certifications",
                                "volunteering", "languages", "awards", "publications", "referees"],
                 section_titles={"skills": "Transferable Skills", "projects": "Relevant Projects"},
                 parsing_notes=_ATS),
    TemplateSpec(id="international", name="International Professional",
                 description="Unicode-safe font for international names; languages raised; unambiguous dates.",
                 recommended_for=["International applicants", "Relocation", "Multilingual roles"],
                 font="dejavu_sans", accent="#155E75", heading_style="caps_rule",
                 section_order=["summary", "experience", "education", "languages", "skills", "certifications",
                                "projects", "awards", "volunteering", "publications", "referees"],
                 parsing_notes=_ATS + " DejaVu Sans covers Latin, Greek and Cyrillic scripts."),
    TemplateSpec(id="minimal_elegant", name="Minimal Elegant",
                 description="Generous whitespace, centred serif name, letter-spaced headings, no rules.",
                 recommended_for=["Consulting", "Law", "Design-adjacent roles"], font="caladea", accent="#6B7280",
                 heading_style="spaced", name_align="center", name_size=22, spacing=1.15, bullet="–",
                 parsing_notes=_ATS),
    TemplateSpec(id="creative_portfolio", name="Creative Portfolio",
                 description="Bold coloured banner and sidebar with geometric type — for creative applications.",
                 recommended_for=["Designers", "Marketing", "Content creators"], layout="sidebar",
                 presentation_oriented=True, font="poppins", accent="#7C3AED", heading_style="shaded",
                 name_banner=True, sidebar_sections=["skills", "languages", "certifications", "awards"],
                 section_order=["summary", "experience", "projects", "education", "skills", "languages",
                                "certifications", "awards", "volunteering", "publications", "referees"],
                 parsing_notes="Presentation-oriented: banner, colour and two columns are for human readers. "
                               "Use the parsing-friendly export for online applications."),
]

TEMPLATE_MAP = {t.id: t for t in TEMPLATES}
DEFAULT_TEMPLATE = "classic_ats"


def get_template(template_id: str | None) -> TemplateSpec:
    return TEMPLATE_MAP.get(template_id or DEFAULT_TEMPLATE, TEMPLATE_MAP[DEFAULT_TEMPLATE])


def recommended_templates(sector: str, career_stage: str) -> list[str]:
    from src.services.taxonomy import SECTORS

    rec = list(SECTORS.get(sector, {}).get("templates", []))
    stage = {"graduate": "graduate_starter", "career_changer": "career_transition",
             "researcher": "academic_research", "executive": "compact_executive"}.get(career_stage)
    if stage:
        rec.insert(0, stage)
    out = []
    for r in rec + ["classic_ats"]:
        if r not in out:
            out.append(r)
    return out[:4]


class RenderOptions(BaseModel):
    page_size: Literal["A4", "Letter"] = "A4"
    page_target: Literal["1", "2", "academic"] = "1"
    font: str | None = None
    accent: str | None = None
    body_size: float | None = None
    alignment: Literal["left", "justify"] = "left"
    date_format: Literal["short", "numeric"] = "short"
    max_bullets_per_role: int = 0
    disabled_sections: list[str] = Field(default_factory=list)
    section_order: list[str] | None = None
    tailor_bullet_order: bool = True
