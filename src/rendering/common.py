from __future__ import annotations

from dataclasses import dataclass, field

from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm

DENSITY = [  # spacing factor, margin factor, body-size delta
    (1.00, 1.00, 0.0),
    (0.86, 0.90, 0.0),
    (0.74, 0.80, 0.0),
    (0.64, 0.72, -0.5),
]
BASE_MARGIN = 16 * mm


def page_size(name: str):
    return LETTER if name == "Letter" else A4


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def tint(h: str, amount: float) -> str:
    """Mix colour with white (amount 0..1 of white)."""
    r, g, b = hex_to_rgb(h)
    mix = lambda c: int(round((c + (1 - c) * amount) * 255))
    return "#{:02X}{:02X}{:02X}".format(mix(r), mix(g), mix(b))


def is_hex(h: str | None) -> bool:
    import re

    return bool(h and re.fullmatch(r"#[0-9A-Fa-f]{6}", h))


@dataclass
class RenderInfo:
    pages: int = 0
    density: int = 0
    body_size: float = 10.5
    margin_mm: float = 16.0
    font: str = ""
    overflow: bool = False
    notes: list[str] = field(default_factory=list)
    expected_order: list[str] = field(default_factory=list)
    single_column: bool = True

    def as_dict(self) -> dict:
        return {"pages": self.pages, "density": self.density, "body_size": self.body_size,
                "margin_mm": self.margin_mm, "font": self.font, "overflow": self.overflow,
                "notes": list(self.notes), "expected_order": list(self.expected_order),
                "single_column": self.single_column}
