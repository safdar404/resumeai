"""Lenient date parsing for resume dates (free text in, structured checks out)."""
from __future__ import annotations

import datetime as _dt
import re

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PRESENT_WORDS = {"present", "current", "now", "ongoing", "today", "till date", "to date"}

DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{1,2}/\d{4}|\d{4}-\d{2})\s*(?:-|–|—|to|until)\s*"
    r"(?P<end>(?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{1,2}/\d{4}|\d{4}-\d{2}|present|current|now|ongoing|till date|to date)",
    re.IGNORECASE,
)


def today() -> tuple[int, int]:
    d = _dt.date.today()
    return d.year, d.month


def is_present(text: str) -> bool:
    return text.strip().lower() in PRESENT_WORDS


def parse_date(text: str) -> tuple[int, int | None] | None:
    """Return (year, month or None). None when unparseable."""
    if not text:
        return None
    t = text.strip().lower().replace(",", " ").replace(".", " ")
    if t in PRESENT_WORDS:
        return today()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", t)
    if m:
        mo = int(m.group(2))
        return (int(m.group(1)), mo) if 1 <= mo <= 12 else None
    m = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{4})", t)
    if m:
        mo = int(m.group(1))
        return (int(m.group(2)), mo) if 1 <= mo <= 12 else None
    m = re.fullmatch(r"([a-z]{3,9})\s+(\d{4})", t)
    if m and m.group(1)[:3] in MONTHS:
        return int(m.group(2)), MONTHS[m.group(1)[:3]]
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        return int(m.group(1)), None
    return None


def format_date(text: str, style: str = "short") -> str:
    """Normalise a date for display; unparseable text is returned unchanged."""
    if not text:
        return ""
    if is_present(text):
        return "Present"
    p = parse_date(text)
    if not p:
        return text.strip()
    y, m = p
    if m is None:
        return str(y)
    if style == "numeric":
        return f"{m:02d}/{y}"
    return f"{MONTH_ABBR[m]} {y}"


def format_range(start: str, end: str, current: bool = False, style: str = "short") -> str:
    s = format_date(start, style)
    e = "Present" if current else format_date(end, style)
    if s and e:
        return f"{s} – {e}"
    return s or e


def months_between(start: str, end: str, current: bool = False) -> int | None:
    a = parse_date(start)
    b = today() if (current or is_present(end)) else parse_date(end)
    if not a or not b:
        return None
    return (b[0] - a[0]) * 12 + ((b[1] or 6) - (a[1] or 6))


def range_problem(start: str, end: str, current: bool = False) -> str | None:
    """Describe a contradiction in a date range, or None."""
    if current and end and not is_present(end):
        return "is marked current but also has an end date"
    a = parse_date(start) if start else None
    if start and not a:
        return f"has an unrecognised start date '{start}'"
    if end and not is_present(end) and not parse_date(end):
        return f"has an unrecognised end date '{end}'"
    b = parse_date(end) if end and not is_present(end) else None
    now = today()
    if a and (a[0], a[1] or 1) > now:
        return "starts in the future"
    if a and b:
        if (b[0], b[1] or 12) < (a[0], a[1] or 1):
            return "ends before it starts"
    return None


def total_experience_years(experiences) -> float:
    """Total months across roles, merging overlaps, expressed in years."""
    spans = []
    for e in experiences:
        a = parse_date(e.start_date)
        b = today() if (e.current or is_present(e.end_date)) else parse_date(e.end_date)
        if a and b:
            s = a[0] * 12 + (a[1] or 1)
            f = b[0] * 12 + (b[1] or 12)
            if f >= s:
                spans.append((s, f))
    spans.sort()
    total, cur = 0, None
    for s, f in spans:
        if cur is None or s > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [s, f]
        else:
            cur[1] = max(cur[1], f)
    if cur:
        total += cur[1] - cur[0]
    return round(total / 12, 1)
