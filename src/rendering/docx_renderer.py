"""DOCX rendering with python-docx from the same ResumeDocument as the PDF.

Uses real Word heading styles for section titles, right tab stops (not
tables) for date alignment in single-column templates, built-in list
bullets, and no headers/footers, so content stays parseable."""
from __future__ import annotations

import io

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from src.models.resume import ResumeDocument, ResumeEntry, ResumeSection
from src.rendering.common import export_document, is_hex, tint
from src.rendering.fonts import FONTS
from src.templates.registry import RenderOptions, TemplateSpec

INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x4A, 0x4A, 0x4A)


def _rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h.lstrip("#").upper())


def _set_font(run_or_style, name: str):
    run_or_style.font.name = name
    el = run_or_style.element if hasattr(run_or_style, "element") else run_or_style._element
    rpr = el.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)


def _border(paragraph, side: str, color: str, size: int = 6, space: int = 1):
    ppr = paragraph._p.get_or_add_pPr()
    pbdr = ppr.find(qn("w:pBdr"))
    if pbdr is None:
        pbdr = OxmlElement("w:pBdr")
        ppr.append(pbdr)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(size)); el.set(qn("w:space"), str(space))
    el.set(qn("w:color"), color.lstrip("#"))
    pbdr.append(el)


def _shade(paragraph_or_cell, color: str, cell: bool = False):
    target = paragraph_or_cell._tc.get_or_add_tcPr() if cell else paragraph_or_cell._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color.lstrip("#"))
    target.append(shd)


def _spacing(p, before: float = 0, after: float = 0, line: float | None = None):
    pf = p.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after)
    if line:
        pf.line_spacing = line


class _Ctx:
    def __init__(self, spec: TemplateSpec, options: RenderOptions, font: str, body: float, sp: float, accent: str,
                 text_width_mm: float):
        self.spec, self.options, self.font, self.body, self.sp, self.accent = spec, options, font, body, sp, accent
        self.width_mm = text_width_mm


def _heading(container, title: str, ctx: _Ctx, doc_styles_ok: bool = True):
    spec = ctx.spec
    style = spec.heading_style
    text = title.upper() if style in ("caps_rule", "shaded", "spaced") else title
    p = container.add_paragraph(style="Heading 1" if doc_styles_ok else None)
    run = p.add_run(text)
    _set_font(run, ctx.font)
    run.font.size = Pt(ctx.body + (0.5 if style in ("caps_rule", "shaded", "spaced") else 1.5))
    run.font.bold = True
    run.font.color.rgb = INK if style in ("plain", "bar") else _rgb(ctx.accent)
    if style == "underline":
        run.font.underline = True
    _spacing(p, before=8 * ctx.sp, after=3 * ctx.sp)
    p.paragraph_format.keep_with_next = True
    if style == "caps_rule":
        _border(p, "bottom", ctx.accent, 6)
    elif style == "rule":
        _border(p, "bottom", "#B8B8B8", 4)
    elif style == "bar":
        _border(p, "left", ctx.accent, 24, 6)
    elif style == "shaded":
        _shade(p, tint(ctx.accent, 0.86))
    elif style == "spaced":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def _para(container, text: str, ctx: _Ctx, *, size: float | None = None, bold=False, italic=False, color=None,
          style: str | None = None, after: float = 1.5, align=None):
    p = container.add_paragraph(style=style) if style else container.add_paragraph()
    if text:
        r = p.add_run(text)
        _set_font(r, ctx.font)
        r.font.size = Pt(size or ctx.body); r.font.bold = bold; r.font.italic = italic
        r.font.color.rgb = color or INK
    _spacing(p, after=after * ctx.sp)
    if align is not None:
        p.alignment = align
    elif ctx.options.alignment == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def _tab_line(container, left: str, right: str, ctx: _Ctx, width_mm: float, *, bold=False, italic=False):
    p = container.add_paragraph()
    p.paragraph_format.tab_stops.add_tab_stop(Mm(width_mm), WD_TAB_ALIGNMENT.RIGHT)
    r = p.add_run(left); _set_font(r, ctx.font); r.font.size = Pt(ctx.body); r.font.bold = bold
    r.font.italic = italic; r.font.color.rgb = MUTED if italic else INK
    if right:
        r2 = p.add_run("\t" + right); _set_font(r2, ctx.font); r2.font.size = Pt(ctx.body - 0.5); r2.font.color.rgb = MUTED
    _spacing(p, after=0)
    p.paragraph_format.keep_with_next = True
    return p


def _entry(container, e: ResumeEntry, ctx: _Ctx, width_mm: float):
    spec = ctx.spec
    first, second = (e.subheading, e.heading) if spec.entry_order == "org_first" else (e.heading, e.subheading)
    if spec.date_style == "inline":
        p = container.add_paragraph()
        for txt, b, i in ((first, True, False), (", " + second if second else "", False, True),
                          (", " + e.location if e.location else "", False, False),
                          (" — " + e.dates if e.dates else "", False, False)):
            if txt:
                r = p.add_run(txt); _set_font(r, ctx.font); r.font.size = Pt(ctx.body); r.font.bold = b; r.font.italic = i
        _spacing(p, after=0); p.paragraph_format.keep_with_next = True
    else:
        _tab_line(container, first, e.dates, ctx, width_mm, bold=True)
        if second or e.location:
            _tab_line(container, second or "", e.location if second else e.location, ctx, width_mm, italic=True) \
                if second else _tab_line(container, e.location, "", ctx, width_mm, italic=True)
    if e.meta:
        p = _para(container, e.meta, ctx, size=ctx.body - 0.5, italic=True, color=MUTED, after=1)
        p.paragraph_format.keep_with_next = bool(e.bullets)
    for i, b in enumerate(e.bullets):
        p = _para(container, b, ctx, style="List Bullet", after=1.2)
        if i == 0:
            p.paragraph_format.keep_together = True
    spacer = container.add_paragraph()
    _spacing(spacer, after=0)
    spacer.paragraph_format.line_spacing = Pt(3.5 * ctx.sp + 1)


def _section(container, sec: ResumeSection, ctx: _Ctx, width_mm: float, side: bool = False):
    if side:
        p = _para(container, sec.title.upper() if ctx.spec.heading_style in ("caps_rule", "shaded") else sec.title, ctx,
                  bold=True, color=_rgb(ctx.accent), after=2, style="Heading 2")
        p.paragraph_format.keep_with_next = True
    else:
        _heading(container, sec.title, ctx)
    if sec.kind == "text":
        _para(container, sec.text, ctx)
    elif sec.kind == "inline":
        if side:
            for it in sec.items:
                _para(container, it, ctx, size=ctx.body - 0.5, after=1)
        else:
            _para(container, ", ".join(sec.items), ctx)
    elif sec.kind == "list":
        for it in sec.items:
            if sec.key == "skills" and ": " in it and len(it.split(": ", 1)[0]) <= 30:
                lbl, rest = it.split(": ", 1)
                p = container.add_paragraph()
                r1 = p.add_run(lbl + ": "); _set_font(r1, ctx.font); r1.font.bold = True; r1.font.size = Pt(ctx.body)
                r2 = p.add_run(rest); _set_font(r2, ctx.font); r2.font.size = Pt(ctx.body)
                _spacing(p, after=1.5 * ctx.sp)
            elif side:
                _para(container, it, ctx, size=ctx.body - 0.5, after=1)
            else:
                _para(container, it, ctx, style="List Bullet", after=1.2)
    else:
        for e in sec.entries:
            _entry(container, e, ctx, width_mm)


def _fix_table_widths(tbl, widths_mm: list[float]) -> None:
    """Word and LibreOffice ignore cell widths unless the layout is fixed and
    the grid columns carry the same widths."""
    tblPr = tbl._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(sum(widths_mm) * 56.7)))
    for col, w in zip(tbl._tbl.tblGrid.findall(qn("w:gridCol")), widths_mm):
        col.set(qn("w:w"), str(int(w * 56.7)))
    for i, col in enumerate(tbl.columns):
        col.width = Mm(widths_mm[i])
    # no extra cell margins on the right column so tab stops line up
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("left", 113), ("right", 113)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val)); el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)


def render_docx(doc: ResumeDocument, spec: TemplateSpec, options: RenderOptions, *, font_key: str | None = None,
                margin_mm: float = 16.0, body_size: float | None = None, density_spacing: float = 1.0,
                force_single: bool = False) -> bytes:
    doc = export_document(doc)
    font_key = font_key or (options.font if options.font in FONTS else spec.font)
    font = FONTS.get(font_key, FONTS["carlito"])["docx"]
    accent = options.accent if is_hex(options.accent) else spec.accent
    body = body_size or options.body_size or spec.body_size
    d = Document()
    sec = d.sections[0]
    if options.page_size == "Letter":
        sec.page_width, sec.page_height = Mm(215.9), Mm(279.4)
    else:
        sec.page_width, sec.page_height = Mm(210), Mm(297)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Mm(margin_mm))
    width_mm = (sec.page_width.mm - 2 * margin_mm)
    normal = d.styles["Normal"]
    _set_font(normal, font); normal.font.size = Pt(body)
    for sname in ("List Bullet", "Heading 1", "Heading 2"):
        st = d.styles[sname]
        _set_font(st, font)
        st.font.color.rgb = INK
    d.styles["Heading 1"].font.size = Pt(body + 1.5)
    d.styles["Heading 2"].font.size = Pt(body)
    d.core_properties.title = f"{doc.name} — Resume" if doc.name else "Resume"
    d.core_properties.author = doc.name
    d.core_properties.comments = "Generated by CareerRainbow AI"
    ctx = _Ctx(spec, options, font, body, density_spacing, accent, width_mm)
    sections = doc.enabled_sections()
    center = WD_ALIGN_PARAGRAPH.CENTER if spec.name_align == "center" else WD_ALIGN_PARAGRAPH.LEFT
    sidebar = spec.layout == "sidebar" and not force_single

    name_p = _para(d, doc.name, ctx, size=spec.name_size, bold=True, after=1, align=center)
    if sidebar and spec.name_banner:
        _shade(name_p, accent)
        for r in name_p.runs:
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    if doc.headline:
        _para(d, doc.headline, ctx, size=body + 1, italic=spec.font != "poppins", color=_rgb(accent), after=2, align=center)
    if not sidebar:
        cp = _para(d, "  |  ".join(doc.contact_items), ctx, size=body - 0.5, color=MUTED, after=4, align=center)
        if spec.heading_style in ("caps_rule", "rule", "bar", "shaded", "accent_text", "underline") and spec.name_align == "left":
            _border(cp, "bottom", accent, 10, 4)
        for s in sections:
            _section(d, s, ctx, width_mm)
    else:
        side_w = width_mm * 0.31
        main_w = width_mm - side_w - 4
        tbl = d.add_table(rows=1, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        left, right = tbl.rows[0].cells
        _fix_table_widths(tbl, [side_w, main_w + 4])
        left.width, right.width = Mm(side_w), Mm(main_w + 4)
        _shade(left, tint(accent, 0.9), cell=True)
        left.paragraphs[0].text = ""
        lp = left.paragraphs[0]
        r = lp.add_run("CONTACT" if spec.heading_style in ("caps_rule", "shaded") else "Contact")
        _set_font(r, font); r.font.bold = True; r.font.color.rgb = _rgb(accent); r.font.size = Pt(body)
        for c in doc.contact_items:
            _para(left, c, ctx, size=body - 0.5, after=1)
        for s in sections:
            if s.sidebar:
                _section(left, s, ctx, side_w, side=True)
        right.paragraphs[0].text = ""
        for s in sections:
            if not s.sidebar:
                _section(right, s, ctx, main_w + 4 - 4.2)
        if right.paragraphs and not right.paragraphs[0].text:
            right._tc.remove(right.paragraphs[0]._p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
