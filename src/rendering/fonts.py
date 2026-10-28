"""Bundled open-licence TTF fonts (see assets/fonts/FONT_LICENSES.md).

Each family has a PDF implementation (embedded TTF) and a DOCX font name.
DOCX names are metric-compatible system fonts so Word layout stays close to
the PDF (Carlito ≈ Calibri, Caladea ≈ Cambria, Liberation ≈ Arial / Times)."""
from __future__ import annotations

from functools import lru_cache

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from src.config import FONTS_DIR

FONTS: dict[str, dict] = {
    "carlito": {"label": "Carlito (Calibri-compatible sans)", "files": ("Carlito-Regular", "Carlito-Bold", "Carlito-Italic", "Carlito-BoldItalic"), "docx": "Calibri"},
    "caladea": {"label": "Caladea (Cambria-compatible serif)", "files": ("Caladea-Regular", "Caladea-Bold", "Caladea-Italic", "Caladea-BoldItalic"), "docx": "Cambria"},
    "liberation_sans": {"label": "Liberation Sans (Arial-compatible)", "files": ("LiberationSans-Regular", "LiberationSans-Bold", "LiberationSans-Italic", "LiberationSans-BoldItalic"), "docx": "Arial"},
    "liberation_serif": {"label": "Liberation Serif (Times-compatible)", "files": ("LiberationSerif-Regular", "LiberationSerif-Bold", "LiberationSerif-Italic", "LiberationSerif-BoldItalic"), "docx": "Times New Roman"},
    "dejavu_sans": {"label": "DejaVu Sans (wide Unicode coverage)", "files": ("DejaVuSans", "DejaVuSans-Bold", "DejaVuSans-Oblique", "DejaVuSans-BoldOblique"), "docx": "Verdana"},
    "dejavu_serif": {"label": "DejaVu Serif (wide Unicode coverage)", "files": ("DejaVuSerif", "DejaVuSerif-Bold", "DejaVuSerif-Italic", "DejaVuSerif-BoldItalic"), "docx": "Georgia"},
    "poppins": {"label": "Poppins (geometric, creative)", "files": ("Poppins-Regular", "Poppins-Bold", "Poppins-Italic", "Poppins-BoldItalic"), "docx": "Century Gothic"},
}
SERIF = {"caladea", "liberation_serif", "dejavu_serif"}


@lru_cache(maxsize=None)
def register(key: str) -> dict[str, str]:
    """Register a family with ReportLab; returns names for regular/bold/italic/bolditalic."""
    if key not in FONTS:
        key = "carlito"
    names = {}
    for variant, fname in zip(("regular", "bold", "italic", "bolditalic"), FONTS[key]["files"]):
        rl_name = f"CR-{fname}"
        if rl_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(rl_name, str(FONTS_DIR / f"{fname}.ttf")))
        names[variant] = rl_name
    pdfmetrics.registerFontFamily(f"CR-{key}", normal=names["regular"], bold=names["bold"],
                                  italic=names["italic"], boldItalic=names["bolditalic"])
    names["family"] = f"CR-{key}"
    return names


@lru_cache(maxsize=None)
def _cmap(key: str) -> frozenset[int]:
    names = register(key)
    face = pdfmetrics.getFont(names["regular"]).face
    return frozenset(face.charToGlyph.keys())


def missing_chars(key: str, text: str) -> set[str]:
    cmap = _cmap(key)
    return {ch for ch in set(text) if not ch.isspace() and ord(ch) not in cmap}


def choose_font(preferred: str, text: str) -> tuple[str, str | None]:
    """Return a font that covers the text, plus a note if a fallback was needed."""
    if not missing_chars(preferred, text):
        return preferred, None
    fallback = "dejavu_serif" if preferred in SERIF else "dejavu_sans"
    missing = missing_chars(fallback, text)
    if not missing:
        return fallback, (f"{FONTS[preferred]['label'].split(' (')[0]} lacks some characters in your text; "
                          f"{FONTS[fallback]['label'].split(' (')[0]} was used so names render correctly.")
    sample = "".join(sorted(missing))[:10]
    return fallback, (f"Some characters ({sample}) are not covered by the bundled fonts (e.g. CJK or some scripts); "
                      "they may not display in the PDF. The DOCX will use your computer's fonts.")
