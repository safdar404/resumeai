"""Occupational taxonomy used by deterministic job analysis, evidence
matching and factual review. Terms are lower-case; matching is word-bounded."""
from __future__ import annotations

import re
from functools import lru_cache

SECTORS: dict[str, dict] = {
    "gis": {
        "label": "GIS, Remote Sensing & GeoAI",
        "terms": ["gis", "arcgis", "arcgis pro", "qgis", "remote sensing", "geoai", "spatial analysis",
                  "geospatial", "cartography", "lidar", "gnss", "gps", "postgis", "geodatabase", "esri",
                  "google earth engine", "sentinel", "landsat", "satellite imagery", "image classification",
                  "photogrammetry", "web mapping", "leaflet", "openlayers", "geoserver", "erdas", "envi",
                  "raster", "vector data", "spatial data", "land cover", "change detection", "drone", "uav",
                  "geopandas", "gdal", "rasterio", "map production", "geocoding", "topographic"],
        "templates": ["gis_geoai", "technical_engineer", "classic_ats"],
    },
    "ai_ml": {
        "label": "AI/ML & Data Science",
        "terms": ["machine learning", "deep learning", "data science", "python", "r", "pytorch", "tensorflow",
                  "keras", "scikit-learn", "nlp", "computer vision", "llm", "large language models",
                  "generative ai", "langchain", "langgraph", "rag", "mlops", "feature engineering",
                  "statistics", "statistical modeling", "pandas", "numpy", "xgboost", "transformers",
                  "hugging face", "model deployment", "a/b testing", "experimentation", "jupyter", "spark",
                  "neural networks", "time series", "forecasting", "reinforcement learning", "prompt engineering"],
        "templates": ["ai_data", "technical_engineer", "classic_ats"],
    },
    "software": {
        "label": "Software Engineering",
        "terms": ["software engineering", "java", "javascript", "typescript", "c#", "c++", "go", "rust",
                  "python", "react", "angular", "vue", "node.js", "django", "flask", "fastapi", "spring",
                  ".net", "rest api", "graphql", "microservices", "docker", "kubernetes", "aws", "azure", "gcp",
                  "ci/cd", "git", "unit testing", "test automation", "sql", "nosql", "mongodb", "redis",
                  "linux", "agile", "scrum", "system design", "devops", "terraform", "html", "css"],
        "templates": ["technical_engineer", "classic_ats", "modern_professional"],
    },
    "analytics": {
        "label": "Data Analytics & Business Intelligence",
        "terms": ["data analysis", "data analytics", "business intelligence", "power bi", "tableau", "looker",
                  "excel", "advanced excel", "sql", "dax", "data visualization", "dashboards", "kpi",
                  "reporting", "etl", "data modeling", "data warehouse", "snowflake", "bigquery", "python",
                  "r", "statistics", "stakeholder management", "data cleaning", "pivot tables", "ssrs", "ssis"],
        "templates": ["ai_data", "classic_ats", "modern_professional"],
    },
    "civil": {
        "label": "Civil Engineering, BIM & Infrastructure",
        "terms": ["civil engineering", "bim", "revit", "autocad", "civil 3d", "navisworks", "structural analysis",
                  "etabs", "sap2000", "staad pro", "geotechnical", "hydraulics", "drainage", "highway design",
                  "infrastructure", "construction management", "site supervision", "quantity surveying",
                  "boq", "primavera p6", "ms project", "building codes", "eurocode", "aci", "surveying",
                  "transportation", "water resources", "environmental impact assessment", "contract administration",
                  "fidic", "health and safety"],
        "templates": ["technical_engineer", "project_manager", "classic_ats"],
    },
    "project_management": {
        "label": "Project Management",
        "terms": ["project management", "pmp", "prince2", "agile", "scrum", "kanban", "waterfall",
                  "stakeholder management", "risk management", "budget management", "scheduling",
                  "ms project", "primavera p6", "jira", "confluence", "resource planning", "change management",
                  "program management", "portfolio management", "vendor management", "procurement",
                  "scope management", "status reporting", "pmo", "capm", "safe"],
        "templates": ["project_manager", "compact_executive", "classic_ats"],
    },
    "healthcare": {
        "label": "Healthcare",
        "terms": ["patient care", "clinical", "nursing", "registered nurse", "ehr", "emr", "epic", "cerner",
                  "medication administration", "triage", "bls", "acls", "pals", "infection control",
                  "patient safety", "hipaa", "care planning", "phlebotomy", "vital signs", "icu", "emergency",
                  "pharmacy", "public health", "clinical documentation", "wound care", "health education",
                  "medical terminology", "diagnosis", "rehabilitation"],
        "templates": ["healthcare", "classic_ats", "international"],
    },
    "finance": {
        "label": "Finance & Accounting",
        "terms": ["accounting", "financial reporting", "ifrs", "gaap", "audit", "external audit", "internal audit",
                  "tax", "taxation", "budgeting", "forecasting", "financial modeling", "financial analysis",
                  "accounts payable", "accounts receivable", "reconciliation", "general ledger", "month-end close",
                  "sap", "oracle financials", "quickbooks", "xero", "excel", "acca", "cpa", "cfa", "ca", "cima",
                  "variance analysis", "payroll", "treasury", "cash flow", "valuation", "compliance"],
        "templates": ["finance", "classic_ats", "compact_executive"],
    },
    "education": {
        "label": "Education",
        "terms": ["teaching", "lesson planning", "curriculum development", "classroom management", "assessment",
                  "differentiated instruction", "student engagement", "e-learning", "lms", "moodle",
                  "google classroom", "pedagogy", "special education", "esl", "tefl", "celta", "tutoring",
                  "academic advising", "instructional design", "parent communication", "stem", "early years"],
        "templates": ["academic_research", "graduate_starter", "classic_ats"],
    },
    "sales_marketing_admin": {
        "label": "Sales, Marketing & Administration",
        "terms": ["sales", "business development", "lead generation", "crm", "salesforce", "hubspot",
                  "account management", "negotiation", "cold calling", "pipeline management", "marketing",
                  "digital marketing", "seo", "sem", "social media", "content marketing", "email marketing",
                  "google analytics", "campaign management", "brand management", "market research",
                  "customer service", "administration", "office management", "scheduling", "data entry",
                  "microsoft office", "bookkeeping", "event coordination", "copywriting"],
        "templates": ["modern_professional", "classic_ats", "creative_portfolio"],
    },
}

SECTOR_LABELS = {k: v["label"] for k, v in SECTORS.items()}
SECTOR_LABELS["general"] = "General / other"

# Terms meaning the same thing (first element = canonical display).
SYNONYMS: list[list[str]] = [
    ["machine learning", "ml"], ["artificial intelligence", "ai"], ["deep learning", "dl"],
    ["natural language processing", "nlp"], ["large language models", "llm", "llms"],
    ["gis", "geographic information systems", "geographic information system"],
    ["remote sensing", "earth observation", "eo"], ["javascript", "js"], ["typescript", "ts"],
    ["kubernetes", "k8s"], ["postgresql", "postgres"], ["ci/cd", "continuous integration", "cicd"],
    ["power bi", "powerbi"], ["microsoft excel", "excel", "ms excel"], ["scikit-learn", "sklearn"],
    ["user experience", "ux"], ["electronic health records", "ehr", "emr", "electronic medical records"],
    ["building information modelling", "bim", "building information modeling"],
    ["project management professional", "pmp"], ["search engine optimization", "seo"],
    ["customer relationship management", "crm"], ["unmanned aerial vehicle", "uav", "drone"],
    ["amazon web services", "aws"], ["google cloud", "gcp", "google cloud platform"],
    ["microsoft azure", "azure"], ["node.js", "nodejs", "node"], ["c#", "csharp"],
    ["rest api", "restful api", "rest apis", "restful apis"], ["a/b testing", "ab testing", "split testing"],
    ["data visualization", "data visualisation"], ["data modeling", "data modelling"],
    ["statistical modeling", "statistical modelling"], ["financial modeling", "financial modelling"],
    ["month-end close", "month end close"], ["english as a second language", "esl"],
]

# Related-but-different skills; evidence in the same family = transferable.
FAMILIES: dict[str, list[str]] = {
    "relational databases": ["sql", "postgresql", "mysql", "oracle", "sql server", "sqlite", "postgis"],
    "cloud platforms": ["aws", "azure", "gcp"],
    "bi tools": ["power bi", "tableau", "looker", "qlik", "ssrs"],
    "desktop gis": ["arcgis", "arcgis pro", "qgis", "erdas", "envi"],
    "deep learning frameworks": ["pytorch", "tensorflow", "keras", "jax"],
    "agile methods": ["agile", "scrum", "kanban", "safe"],
    "pm certifications": ["pmp", "prince2", "capm"],
    "cad/bim": ["autocad", "revit", "civil 3d", "navisworks", "microstation", "bim"],
    "structural software": ["etabs", "sap2000", "staad pro"],
    "scheduling tools": ["ms project", "primavera p6"],
    "accounting standards": ["ifrs", "gaap"],
    "accounting software": ["sap", "oracle financials", "quickbooks", "xero"],
    "ehr systems": ["epic", "cerner", "ehr"],
    "life support": ["bls", "acls", "pals"],
    "frontend frameworks": ["react", "angular", "vue"],
    "backend frameworks": ["django", "flask", "fastapi", "spring", ".net", "node.js"],
    "programming languages": ["python", "java", "javascript", "typescript", "c#", "c++", "go", "rust", "r"],
    "crm platforms": ["salesforce", "hubspot", "crm"],
    "web mapping": ["leaflet", "openlayers", "geoserver", "web mapping"],
    "satellite data": ["sentinel", "landsat", "satellite imagery", "remote sensing"],
    "lms": ["moodle", "google classroom", "lms"],
    "teaching certificates": ["tefl", "celta", "esl"],
    "containers": ["docker", "kubernetes"],
    "data wrangling": ["pandas", "numpy", "data cleaning", "excel"],
    "ml libraries": ["scikit-learn", "xgboost", "pytorch", "tensorflow"],
}

# Correct casing for technical terms in prose.
TECH_CASING = {
    "python": "Python", "pythn": "Python", "javascript": "JavaScript", "typescript": "TypeScript",
    "postgresql": "PostgreSQL", "postgis": "PostGIS", "mysql": "MySQL", "arcgis": "ArcGIS",
    "qgis": "QGIS", "gis": "GIS", "sql": "SQL", "github": "GitHub", "gitlab": "GitLab",
    "tensorflow": "TensorFlow", "pytorch": "PyTorch", "numpy": "NumPy", "matlab": "MATLAB",
    "autocad": "AutoCAD", "revit": "Revit", "linkedin": "LinkedIn", "excel": "Excel",
    "powerbi": "Power BI", "tableau": "Tableau", "docker": "Docker", "kubernetes": "Kubernetes",
    "aws": "AWS", "gcp": "GCP", "html": "HTML", "css": "CSS", "api": "API", "apis": "APIs",
    "lidar": "LiDAR", "uav": "UAV", "gnss": "GNSS", "gps": "GPS", "nlp": "NLP", "llm": "LLM",
    "llms": "LLMs", "bim": "BIM", "etl": "ETL", "kpi": "KPI", "kpis": "KPIs", "crm": "CRM",
    "seo": "SEO", "ehr": "EHR", "ifrs": "IFRS", "gaap": "GAAP", "esri": "Esri", "gdal": "GDAL",
    "javascipt": "JavaScript", "scikit-learn": "scikit-learn", "geopandas": "GeoPandas",
    "langchain": "LangChain", "langgraph": "LangGraph", "jira": "Jira", "sap": "SAP",
}

ACRONYM_OK = {"GIS", "SQL", "API", "AWS", "GCP", "BIM", "KPI", "ETL", "CRM", "SEO", "EHR", "IFRS", "GAAP",
              "NLP", "LLM", "UAV", "GPS", "GNSS", "HTML", "CSS", "PDF", "CV", "BSC", "MSC", "PHD", "MBA",
              "BA", "MA", "UK", "USA", "US", "EU", "UAE", "IT", "HR", "QA", "UI", "UX", "R&D", "CEO", "CTO"}


@lru_cache(maxsize=1)
def _canonical_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for group in SYNONYMS:
        for t in group:
            m[t] = group[0]
    return m


def canonical(term: str) -> str:
    t = term.lower().strip()
    return _canonical_map().get(t, t)


def variants(term: str) -> list[str]:
    c = canonical(term)
    for group in SYNONYMS:
        if group[0] == c:
            return group
    return [c]


@lru_cache(maxsize=1)
def all_terms() -> list[str]:
    terms = set()
    for s in SECTORS.values():
        terms.update(s["terms"])
    for g in SYNONYMS:
        terms.update(g)
    for f in FAMILIES.values():
        terms.update(f)
    # longest first so multi-word terms win
    return sorted(terms, key=lambda t: (-len(t), t))


@lru_cache(maxsize=4096)
def term_pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)


AMBIGUOUS_SHORT = {"r", "go", "ca", "ai", "ml", "eo", "dl", "ts", "js", "node", "sap", "safe", "ux", "excel"}


def find_terms(text: str) -> list[str]:
    """Canonical taxonomy terms present in text (word-bounded)."""
    found: list[str] = []
    seen = set()
    low = text or ""
    for t in all_terms():
        if t in AMBIGUOUS_SHORT:
            # require exact-case or clear context for very short/ambiguous terms
            if t == "r" and not re.search(r"(?<![A-Za-z])R(?![A-Za-z])(?=[\s,/)]|$)", low):
                continue
            if t == "go" and not re.search(r"\bGo(lang)?\b(?! to)", low):
                continue
            if t in ("ca", "ts", "js", "eo", "dl", "safe", "sap", "ux", "ai", "ml") and \
                    not re.search(r"(?<![A-Za-z])" + re.escape(t.upper()) + r"(?![A-Za-z])", low):
                continue
            if t == "node" and not re.search(r"\bNode(\.js)?\b", low):
                continue
        if term_pattern(t).search(low):
            c = canonical(t)
            if c not in seen:
                seen.add(c)
                found.append(c)
    return found


def family_of(term: str) -> list[str]:
    c = canonical(term)
    return [name for name, members in FAMILIES.items() if c in [canonical(x) for x in members]]


def family_members(term: str) -> set[str]:
    out: set[str] = set()
    for name in family_of(term):
        out.update(canonical(x) for x in FAMILIES[name])
    out.discard(canonical(term))
    return out


def detect_sector(text: str) -> str:
    low = text or ""
    best, best_score = "general", 0
    for key, s in SECTORS.items():
        score = sum(1 for t in s["terms"] if len(t) > 2 and term_pattern(t).search(low))
        if score > best_score:
            best, best_score = key, score
    return best if best_score >= 2 else "general"
