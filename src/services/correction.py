"""Deterministic language correction that preserves facts.

Routine fixes (known misspellings, spacing, punctuation, capitalisation,
tense of the opening verb of past-role bullets, technical-term casing) are
applied automatically and recorded. Dictionary-based guesses for unknown
words are only *suggested* and require confirmation. Proper nouns, numbers,
technical terms and anything inside URLs/e-mails are never changed.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.models.corrections import Correction
from src.models.profile import CandidateProfile
from src.services.taxonomy import TECH_CASING, all_terms
from src.services.text_utils import numbers_in

COMMON_MISSPELLINGS = {
    "mange": "manage", "manged": "managed", "manageing": "managing", "managment": "management",
    "databse": "database", "databses": "databases", "datbase": "database", "programing": "programming",
    "programm": "program", "developement": "development", "devlopment": "development", "develope": "develop",
    "experiance": "experience", "expirience": "experience", "responsable": "responsible",
    "responsibilites": "responsibilities", "recieve": "receive", "recieved": "received", "acheive": "achieve",
    "acheived": "achieved", "achived": "achieved", "sucessful": "successful", "succesful": "successful",
    "successfull": "successful", "sucessfully": "successfully", "analysys": "analysis", "analisys": "analysis",
    "analyse": "analyse", "enviroment": "environment", "enviromental": "environmental", "maintainance": "maintenance",
    "maintenence": "maintenance", "comunication": "communication", "communcation": "communication",
    "colaborated": "collaborated", "collaberated": "collaborated", "collegue": "colleague",
    "collegues": "colleagues", "accomodate": "accommodate", "occured": "occurred", "seperate": "separate",
    "definately": "definitely", "independant": "independent", "knowlege": "knowledge", "knowledgable": "knowledgeable",
    "proffesional": "professional", "profesional": "professional", "coordinatd": "coordinated",
    "cordinated": "coordinated", "implemeted": "implemented", "implimented": "implemented",
    "impliment": "implement", "inital": "initial", "intial": "initial", "reasearch": "research",
    "reserch": "research", "reseacher": "researcher", "softwares": "software", "tecnical": "technical",
    "techincal": "technical", "technicial": "technical", "achievment": "achievement", "achievments": "achievements",
    "acheivement": "achievement", "acheivements": "achievements", "buisness": "business", "bussiness": "business",
    "calender": "calendar", "commited": "committed", "comittee": "committee", "concious": "conscious",
    "excercise": "exercise", "goverment": "government", "garantee": "guarantee", "harrass": "harass",
    "liason": "liaison", "neccessary": "necessary", "necesary": "necessary", "noticable": "noticeable",
    "oppurtunity": "opportunity", "oportunity": "opportunity", "persistant": "persistent",
    "posession": "possession", "prefered": "preferred", "priviledge": "privilege", "publically": "publicly",
    "recomend": "recommend", "recomended": "recommended", "refered": "referred", "relevent": "relevant",
    "schedual": "schedule", "sucess": "success", "supervisior": "supervisor", "suprvised": "supervised",
    "tommorow": "tomorrow", "untill": "until", "wich": "which", "writen": "written", "teh": "the",
    "adn": "and", "anaylsis": "analysis", "anaylzed": "analyzed", "analized": "analyzed",
    "visualisaton": "visualisation", "visualizaton": "visualization", "statistcal": "statistical",
    "algorithim": "algorithm", "algoritm": "algorithm", "pipline": "pipeline", "pipelne": "pipeline",
    "infrastucture": "infrastructure", "infrastruture": "infrastructure", "constrution": "construction",
    "engeneering": "engineering", "enginering": "engineering", "enginner": "engineer", "engeneer": "engineer",
    "surveing": "surveying", "mapp": "map", "mapps": "maps", "satelite": "satellite", "sattelite": "satellite",
    "imagry": "imagery", "classifcation": "classification", "clasification": "classification",
    "spacial": "spatial", "geospacial": "geospatial", "analytcs": "analytics", "reprt": "report",
    "reprots": "reports", "stakholders": "stakeholders", "stakeholdres": "stakeholders",
    "acurate": "accurate", "accuracy": "accuracy", "acuracy": "accuracy", "effeciency": "efficiency",
    "efficent": "efficient", "improvment": "improvement", "improvments": "improvements",
    "patiens": "patients", "medicaton": "medication", "accountting": "accounting", "finacial": "financial",
    "finanical": "financial", "budjet": "budget", "teachng": "teaching", "curriculm": "curriculum",
    "studnets": "students", "langauge": "language", "langauges": "languages", "certifcate": "certificate",
    "certfication": "certification", "univeristy": "university", "universty": "university",
    "bachlor": "bachelor", "bachelors": "bachelor's", "masters": "master's",
}

# Verbs commonly used to open resume bullets: base -> past tense.
VERB_PAST = {
    "manage": "managed", "develop": "developed", "lead": "led", "design": "designed", "create": "created",
    "build": "built", "analyze": "analyzed", "analyse": "analysed", "coordinate": "coordinated",
    "implement": "implemented", "maintain": "maintained", "prepare": "prepared", "conduct": "conducted",
    "support": "supported", "train": "trained", "supervise": "supervised", "deliver": "delivered",
    "improve": "improved", "reduce": "reduced", "increase": "increased", "produce": "produced",
    "process": "processed", "collect": "collected", "map": "mapped", "write": "wrote", "teach": "taught",
    "plan": "planned", "organize": "organized", "organise": "organised", "monitor": "monitored",
    "automate": "automated", "integrate": "integrated", "deploy": "deployed", "test": "tested",
    "review": "reviewed", "assist": "assisted", "handle": "handled", "oversee": "oversaw",
    "negotiate": "negotiated", "present": "presented", "research": "researched", "evaluate": "evaluated",
    "assess": "assessed", "launch": "launched", "establish": "established", "streamline": "streamlined",
    "mentor": "mentored", "migrate": "migrated", "optimize": "optimized", "optimise": "optimised",
    "audit": "audited", "reconcile": "reconciled", "administer": "administered", "perform": "performed",
    "provide": "provided", "ensure": "ensured", "work": "worked", "help": "helped", "digitize": "digitized",
    "digitise": "digitised", "survey": "surveyed", "model": "modelled", "classify": "classified",
}
PAST_VALUES = set(VERB_PAST.values())

_URLISH = re.compile(r"(https?://\S+|www\.\S+|\S+@\S+\.\S+|\S+\.(com|org|net|io|edu|gov)\S*)", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")

_spell = None


def _spellchecker():
    global _spell
    if _spell is None:
        try:
            from spellchecker import SpellChecker

            _spell = SpellChecker(language="en", distance=2)
            _spell.word_frequency.load_words(
                [w for t in all_terms() for w in t.split()] + list(TECH_CASING.keys())
                + list(VERB_PAST.keys()) + list(PAST_VALUES) + ["analyse", "organisation", "programme",
                   "modelling", "geospatial", "workflow", "workflows", "dataset", "datasets", "stakeholder",
                   "stakeholders", "onboarding", "upskilled", "scalable", "geoai", "pipelines", "backend",
                   "frontend", "dashboards", "analytics", "visualisation", "realtime"])
        except Exception:
            _spell = False
    return _spell or None


def _match_case(src: str, repl: str) -> str:
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def _protected(word: str, protected: set[str]) -> bool:
    w = word.lower().strip("'’-")
    return w in protected


class _Changes:
    def __init__(self) -> None:
        self.notes: list[str] = []
        self.cats: set[str] = set()

    def add(self, cat: str, note: str) -> None:
        self.cats.add(cat)
        if note not in self.notes:
            self.notes.append(note)


def _fix_words(text: str, protected: set[str], ch: _Changes) -> str:
    spans = [(m.start(), m.end()) for m in _URLISH.finditer(text)]

    def in_span(i: int) -> bool:
        return any(a <= i < b for a, b in spans)

    out, last = [], 0
    for m in _WORD.finditer(text):
        word = m.group(0)
        if in_span(m.start()):
            continue
        low = word.lower()
        repl = None
        if low in TECH_CASING and word != TECH_CASING[low] and not _protected(word, protected - {low}):
            # technical casing (e.g. pythn -> Python) — only for lowercase/garbled tokens
            if word.islower() or low == "pythn":
                repl = TECH_CASING[low]
                ch.add("casing" if low != "pythn" else "spelling",
                       f"'{word}' → '{repl}'")
        elif low in COMMON_MISSPELLINGS and not _protected(word, protected) and COMMON_MISSPELLINGS[low] != low:
            repl = _match_case(word, COMMON_MISSPELLINGS[low])
            ch.add("spelling", f"'{word}' → '{repl}'")
        if repl:
            out.append(text[last:m.start()])
            out.append(repl)
            last = m.end()
    out.append(text[last:])
    return "".join(out)


def _fix_spacing_punct(text: str, ch: _Changes) -> str:
    t = text
    new = re.sub(r"[ \t]{2,}", " ", t).strip()
    if new != t.strip():
        ch.add("formatting", "removed extra spaces")
    t2 = re.sub(r"\s+([,.;:!?])(?=\s|$)", r"\1", new)
    if t2 != new:
        ch.add("punctuation", "removed space before punctuation")
    t3 = re.sub(r"([,;])(?=[A-Za-z])", r"\1 ", t2)
    if t3 != t2:
        ch.add("punctuation", "added space after comma")
    t4 = re.sub(r"([,.;:!?])\1+", r"\1", t3)
    t4 = re.sub(r"(?<!\.)\.\.(?!\.)", ".", t4)
    if t4 != t3:
        ch.add("punctuation", "removed repeated punctuation")
    t5 = re.sub(r"\b([A-Za-z]+)\s+\1\b", lambda m: m.group(1) if m.group(1).lower() not in ("had", "that") else m.group(0),
                t4, flags=re.I)
    if t5 != t4:
        ch.add("grammar", "removed repeated word")
    t6 = re.sub(r"(?<![A-Za-z])i(?![A-Za-z'’.@])", "I", t5)
    if t6 != t5:
        ch.add("grammar", "capitalised 'I'")
    return t6


def _capitalise_first(text: str, ch: _Changes, protected: set[str]) -> str:
    m = re.search(r"[A-Za-z]", text)
    if not m:
        return text
    i = m.start()
    word = _WORD.match(text, i)
    if word and _protected(word.group(0), protected):
        return text  # e.g. "iOS", "eBay" — leave brand casing alone
    if text[i].islower():
        ch.add("formatting", "capitalised the first letter")
        return text[:i] + text[i].upper() + text[i + 1:]
    return text


def _fix_tense(text: str, past_role: bool, ch: _Changes) -> str:
    if not past_role:
        return text
    m = _WORD.match(text.lstrip("•-–* "))
    if not m:
        return text
    offset = len(text) - len(text.lstrip("•-–* "))
    w = m.group(0)
    low = w.lower()
    if low in VERB_PAST:
        repl = _match_case(w, VERB_PAST[low])
        ch.add("tense", f"'{w}' → '{repl}' (past role)")
        return text[:offset] + repl + text[offset + len(w):]
    return text


def _strip_bullet_marker(text: str, ch: _Changes) -> str:
    new = re.sub(r"^\s*[•▪◦●\-–*·]+\s*", "", text)
    if new != text:
        ch.add("formatting", "removed duplicated bullet symbol")
    return new


def correct_text(text: str, *, protected: set[str], is_bullet: bool = False, past_role: bool = False,
                 strip_period: bool = False) -> tuple[str, list[str], set[str]]:
    """Return corrected text, change notes and categories."""
    ch = _Changes()
    t = text
    if is_bullet:
        t = _strip_bullet_marker(t, ch)
    t = _fix_words(t, protected, ch)
    t = _fix_spacing_punct(t, ch)
    if is_bullet:
        t = _fix_tense(t, past_role, ch)
        if strip_period and t.endswith(".") and t.count(". ") == 0 and not t.endswith("etc."):
            t = t[:-1]
            ch.add("formatting", "consistent bullet punctuation (no trailing period)")
    t = _capitalise_first(t, ch, protected)
    return t, ch.notes, ch.cats


def _spelling_suggestions(text: str, protected: set[str]) -> list[tuple[str, str]]:
    sp = _spellchecker()
    if not sp:
        return []
    spans = [(m.start(), m.end()) for m in _URLISH.finditer(text)]
    out = []
    for m in _WORD.finditer(text):
        w = m.group(0)
        if any(a <= m.start() < b for a, b in spans):
            continue
        if len(w) < 5 or not w.islower() or _protected(w, protected) or "'" in w or "-" in w:
            continue
        if w in sp:  # known word
            continue
        cand = sp.correction(w)
        if cand and cand != w and SequenceMatcher(None, w, cand).ratio() >= 0.8:
            out.append((w, cand))
    return out


def facts_preserved(original: str, corrected: str, protected: set[str]) -> tuple[bool, str]:
    """Check a proposed correction keeps numbers and protected terms intact."""
    if numbers_in(original) != numbers_in(corrected):
        return False, "numbers changed"
    orig_tokens = {t.lower() for t in _WORD.findall(original)}
    corr_tokens = {t.lower() for t in _WORD.findall(corrected)}
    lost = {t for t in orig_tokens & protected if t not in corr_tokens}
    if lost:
        return False, "names or technical terms changed: " + ", ".join(sorted(lost))
    if SequenceMatcher(None, original.lower(), corrected.lower()).ratio() < 0.6:
        return False, "the wording changed substantially"
    return True, ""


def bullet_period_style(profile: CandidateProfile) -> bool:
    """True when most bullets have no trailing period (so strip for consistency)."""
    bullets = [b for e in profile.experience for b in e.bullets] + [b for p in profile.projects for b in p.bullets]
    if len(bullets) < 3:
        return False
    no_period = sum(1 for b in bullets if not b.rstrip().endswith("."))
    return no_period > len(bullets) / 2


def run_rule_corrections(profile: CandidateProfile, *, already_checked: dict[str, str] | None = None,
                         rejected: set[str] | None = None) -> list[Correction]:
    """Produce corrections for prose fields that changed since last check."""
    already_checked = already_checked or {}
    rejected = rejected or set()
    protected = profile.protected_terms()
    strip_period = bullet_period_style(profile)
    out: list[Correction] = []
    for path, text in profile.prose_fields():
        if already_checked.get(path) == text:
            continue
        is_bullet = ".bullets[" in path or ".details[" in path
        past = False
        m = re.match(r"experience\[(\d+)\]", path)
        if m:
            e = profile.experience[int(m.group(1))]
            past = bool(e.end_date) and not e.current and e.end_date.lower() not in ("present", "current")
        corrected, notes, cats = correct_text(text, protected=protected, is_bullet=is_bullet,
                                              past_role=past, strip_period=strip_period and is_bullet)
        if corrected != text:
            c = Correction(path=path, original=text, corrected=corrected,
                           explanation="; ".join(notes), categories=sorted(cats))
            if c.signature() not in rejected:
                out.append(c)
            base = corrected
        else:
            base = text
        for wrong, right in _spelling_suggestions(base, protected):
            sug = re.sub(r"(?<![A-Za-z])" + re.escape(wrong) + r"(?![A-Za-z])", right, base, count=1)
            c = Correction(path=path, original=base, corrected=sug,
                           explanation=f"possible misspelling: '{wrong}' → '{right}' (please confirm)",
                           categories=["spelling_suggestion"], requires_confirmation=True, status="pending")
            if c.signature() not in rejected:
                out.append(c)
    # Skill names and proper-noun fields: suggest only, never auto-apply.
    for i, s in enumerate(profile.skills.technical):
        low = s.lower()
        if low in TECH_CASING and s != TECH_CASING[low] and (s.islower() or low == "pythn"):
            c = Correction(path=f"skills.technical[{i}]", original=s, corrected=TECH_CASING[low],
                           explanation="standard spelling of a technical term (skill names are only changed with your approval)",
                           categories=["casing"], requires_confirmation=True, status="pending")
            if c.signature() not in rejected:
                out.append(c)
    return out


def normalise_skill(s: str) -> str:
    return TECH_CASING.get(s.lower(), s)
