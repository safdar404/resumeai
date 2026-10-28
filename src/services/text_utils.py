from __future__ import annotations

import re
import unicodedata

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_STRICT_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{6,}\d)")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:/[^\s,;|]*)?")
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)*(?: ?%)?")
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž][\w'’+#.-]*")

STOPWORDS = set("""a an and are as at be been but by can for from has have in into is it its of on or our
that the their this to was were will with within you your we they them i me my he she his her who whom which
what when where why how all any both each few more most other some such no nor not only own same so than too very
s t just don should now able ability strong excellent good knowledge experience experienced years year using use
work working including include includes etc e.g ie role candidate candidates required requirement requirements
preferred plus must ideal ideally responsibilities responsibility skills skill proven demonstrated familiarity
familiar understanding team teams across new well also per job position opportunity company within based""".split())


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def norm_key(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9+#]+", " ", t).strip()


def numbers_in(text: str) -> set[str]:
    out = set()
    for m in NUMBER_RE.finditer(text or ""):
        n = re.sub(r"\s", "", m.group(0)).replace(",", "")
        out.add(n.rstrip("%"))
    return out


def content_words(text: str) -> list[str]:
    return [w.lower().strip(".-'") for w in WORD_RE.findall(text or "")
            if len(w) > 2 and w.lower().strip(".-'") not in STOPWORDS]


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_STRICT_RE.match(email or ""))


def link_problem(url: str) -> str | None:
    """Describe a problem with a link, or None if it looks complete."""
    u = (url or "").strip()
    if not u:
        return None
    if " " in u:
        return "contains spaces"
    bare = re.sub(r"^https?://", "", u, flags=re.I)
    bare = re.sub(r"^www\.", "", bare, flags=re.I)
    host = bare.split("/")[0]
    if "." not in host or host.endswith(".") or len(host.split(".")[-1]) < 2:
        return "is missing a valid domain"
    path = bare[len(host):].strip("/")
    low = host.lower()
    if "linkedin.com" in low:
        if not re.match(r"^(in|pub|company)/[^/]+", path):
            return "is missing the profile handle (expected linkedin.com/in/your-name)"
    if low in ("github.com", "gitlab.com") and not path:
        return "is missing the username"
    return None


def display_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip(), flags=re.I).rstrip("/")


def first_word(text: str) -> str:
    m = WORD_RE.search(text or "")
    return m.group(0).lower() if m else ""
