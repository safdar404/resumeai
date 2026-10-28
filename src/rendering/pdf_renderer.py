"""PDF rendering with ReportLab. One engine renders all fifteen templates from
the same ResumeDocument; templates only change style tokens and layout.

Fitting strategy (never deletes content): try progressively tighter spacing
and margins, and as a last resort 0.5 pt smaller body text (minimum 10 pt).
If the content still exceeds the page target, the document is produced with
the extra page and the overflow is reported with suggestions."""
from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, FrameBreak, HRFlowable, KeepTogether,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from src.models.resume import ResumeDocument, ResumeEntry, ResumeSection
from src.rendering.common import BASE_MARGIN, DENSITY, RenderInfo, is_hex, page_size, tint
from src.rendering.fonts import choose_font, register
from src.templates.registry import RenderOptions, TemplateSpec

INK = colors.HexColor("#1A1A1A")
MUTED = colors.HexColor("#4A4A4A")


def esc(t: str) -> str:
    return escape(t or "")


class Styles:
    def __init__(self, spec: TemplateSpec, fonts: dict, body: float, sp: float, accent: str, justify: bool,
                 on_dark: bool = False):
        f, fb, fi = fonts["regular"], fonts["bold"], fonts["italic"]
        acc = colors.HexColor(accent)
        lead = body * 1.24
        align = TA_JUSTIFY if justify else TA_LEFT
        self.accent = acc
        self.accent_hex = accent
        self.body_size = body
        self.sp = sp
        name_color = colors.white if on_dark else INK
        self.name = ParagraphStyle("name", fontName=fb, fontSize=spec.name_size, leading=spec.name_size * 1.15,
                                   textColor=name_color, alignment=TA_CENTER if spec.name_align == "center" else TA_LEFT,
                                   spaceAfter=2)
        self.headline = ParagraphStyle("headline", fontName=fi if spec.font != "poppins" else f, fontSize=body + 1,
                                       leading=(body + 1) * 1.25, alignment=self.name.alignment,
                                       textColor=colors.white if on_dark else acc, spaceAfter=2)
        self.contact = ParagraphStyle("contact", fontName=f, fontSize=body - 0.5, leading=(body - 0.5) * 1.3,
                                      alignment=self.name.alignment, textColor=MUTED, spaceAfter=4 * sp)
        hsize = body + 1.5
        self.h = ParagraphStyle("h", fontName=fb, fontSize=hsize, leading=hsize * 1.2, textColor=INK,
                                spaceBefore=8 * sp, spaceAfter=2 * sp, keepWithNext=1)
        self.h_accent = ParagraphStyle("ha", parent=self.h, textColor=acc)
        self.h_caps = ParagraphStyle("hc", parent=self.h, fontSize=body + 0.5, leading=(body + 0.5) * 1.25,
                                     textColor=acc, spaceAfter=1)
        self.h_center = ParagraphStyle("hcen", parent=self.h_caps, alignment=TA_CENTER, textColor=acc,
                                       fontSize=body + 0.5, spaceBefore=10 * sp)
        self.h_plain = ParagraphStyle("hp", parent=self.h, fontSize=body + 2.5, leading=(body + 2.5) * 1.2)
        self.h_shaded = ParagraphStyle("hs", parent=self.h_caps, textColor=colors.HexColor(accent),
                                       backColor=colors.HexColor(tint(accent, 0.86)), borderPadding=(2, 4, 2, 4),
                                       spaceBefore=10 * sp, spaceAfter=4 * sp)
        self.entry_title = ParagraphStyle("et", fontName=fb, fontSize=body, leading=lead, textColor=INK)
        self.entry_sub = ParagraphStyle("es", fontName=fi, fontSize=body, leading=lead, textColor=MUTED)
        self.date = ParagraphStyle("d", fontName=f, fontSize=body - 0.5, leading=lead, textColor=MUTED, alignment=TA_RIGHT)
        self.body = ParagraphStyle("b", fontName=f, fontSize=body, leading=lead, textColor=INK, alignment=align,
                                   spaceAfter=1.5 * sp)
        self.meta = ParagraphStyle("m", fontName=fi, fontSize=body - 0.5, leading=lead, textColor=MUTED, spaceAfter=1)
        self.bullet = ParagraphStyle("bl", parent=self.body, leftIndent=11, bulletIndent=2, bulletFontName=f,
                                     bulletColor=acc, spaceAfter=1.2 * sp)
        self.small = ParagraphStyle("sm", fontName=f, fontSize=body - 0.5, leading=(body - 0.5) * 1.3, textColor=INK,
                                    spaceAfter=2 * sp)
        self.side_h = ParagraphStyle("sh", fontName=fb, fontSize=body, leading=body * 1.3, textColor=acc,
                                     spaceBefore=7 * sp, spaceAfter=2 * sp, keepWithNext=1)


def heading(title: str, spec: TemplateSpec, st: Styles, width: float, style: str | None = None) -> list:
    style = style or spec.heading_style
    t = esc(title)
    if style == "caps_rule":
        return [Paragraph(t.upper(), st.h_caps), HRFlowable(width="100%", thickness=0.7, color=st.accent,
                                                           spaceBefore=1.5, spaceAfter=3 * st.sp)]
    if style == "rule":
        return [Paragraph(t, st.h_accent), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#B8B8B8"),
                                                     spaceBefore=1, spaceAfter=3 * st.sp)]
    if style == "bar":
        tbl = Table([["", Paragraph(t, st.h)]], colWidths=[3, width - 3])
        tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), st.accent), ("LEFTPADDING", (0, 0), (0, 0), 0),
                                 ("LEFTPADDING", (1, 0), (1, 0), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return [Spacer(1, 7 * st.sp), tbl, Spacer(1, 3 * st.sp)]
    if style == "plain":
        return [Paragraph(t, st.h_plain)]
    if style == "underline":
        return [Paragraph(f"<u>{t}</u>", st.h_accent)]
    if style == "shaded":
        return [Paragraph(t.upper(), st.h_shaded)]
    if style == "spaced":
        return [Paragraph(t.upper(), st.h_center), HRFlowable(width="14%", thickness=0.8, color=st.accent,
                                                             hAlign="CENTER", spaceBefore=1, spaceAfter=4 * st.sp)]
    return [Paragraph(t, st.h_accent)]  # accent_text


def _two_col(left, right, width: float, date_w: float) -> Table:
    tbl = Table([[left, right]], colWidths=[width - date_w, date_w])
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return tbl


def entry_flowables(e: ResumeEntry, spec: TemplateSpec, st: Styles, width: float) -> list:
    out: list = []
    date_w = min(40 * mm, width * 0.32)
    first, second = (e.subheading, e.heading) if spec.entry_order == "org_first" else (e.heading, e.subheading)
    if spec.date_style == "inline":
        bits = [f"<b>{esc(first)}</b>"] if first else []
        if second:
            bits.append(f"<i>{esc(second)}</i>")
        if e.location:
            bits.append(esc(e.location))
        line = ", ".join(bits) + (f" — {esc(e.dates)}" if e.dates else "")
        out.append(Paragraph(line, st.entry_title))
    else:
        left1 = Paragraph(f"<b>{esc(first)}</b>" if first else "", st.entry_title)
        out.append(_two_col(left1, Paragraph(esc(e.dates), st.date), width, date_w) if e.dates else left1)
        if second or e.location:
            if second and e.location:
                out.append(_two_col(Paragraph(esc(second), st.entry_sub), Paragraph(esc(e.location), st.date), width, date_w))
            else:
                out.append(Paragraph(esc(second or e.location), st.entry_sub))
    if e.meta:
        out.append(Paragraph(esc(e.meta), st.meta))
    for b in e.bullets:
        out.append(Paragraph(esc(b), st.bullet, bulletText=spec.bullet))
    out.append(Spacer(1, 3.5 * st.sp))
    return out


def section_flowables(sec: ResumeSection, spec: TemplateSpec, st: Styles, width: float, side: bool = False) -> list:
    head = [Paragraph(esc(sec.title).upper() if spec.heading_style in ("caps_rule", "shaded", "spaced") else esc(sec.title),
                      st.side_h)] if side else heading(sec.title, spec, st, width)
    body: list = []
    if sec.kind == "text":
        body = [Paragraph(esc(sec.text), st.body)]
    elif sec.kind == "inline":
        if side:
            body = [Paragraph(esc(i), st.small) for i in sec.items]
        else:
            body = [Paragraph(esc(", ".join(sec.items)), st.body)]
    elif sec.kind == "list":
        for it in sec.items:
            if ": " in it and len(it.split(": ", 1)[0]) <= 30 and sec.key == "skills":
                lbl, rest = it.split(": ", 1)
                body.append(Paragraph(f"<b>{esc(lbl)}:</b> {esc(rest)}", st.small if side else st.body))
            elif side:
                body.append(Paragraph(esc(it), st.small))
            else:
                body.append(Paragraph(esc(it), st.bullet, bulletText=spec.bullet))
    else:
        entries = [entry_flowables(e, spec, st, width) for e in sec.entries]
        if not entries:
            return []
        out = [KeepTogether(head + entries[0])]
        out += [KeepTogether(ef) for ef in entries[1:]]
        return out
    if not body:
        return []
    return [KeepTogether(head + body[:2])] + body[2:]


def header_flowables(doc: ResumeDocument, spec: TemplateSpec, st: Styles, include_contact: bool = True) -> list:
    out = [Paragraph(esc(doc.name), st.name)]
    if doc.headline:
        out.append(Paragraph(esc(doc.headline), st.headline))
    if include_contact and doc.contact_items:
        out.append(Paragraph("  |  ".join(esc(c) for c in doc.contact_items), st.contact))
    if spec.heading_style in ("plain", "spaced") and include_contact:
        out.append(Spacer(1, 2))
    return out


def wrap_link(text: str, font: str, size: float, width: float) -> str:
    """Escape text; if it is a long URL-like token, break it after a '/' or '.'
    boundary instead of mid-word (sidebar columns are narrow)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if " " in text or stringWidth(text, font, size) <= width:
        return esc(text)
    lines, cur = [], ""
    for part in re.split(r"(?<=[/.@-])", text):
        if cur and stringWidth(cur + part, font, size) > width:
            lines.append(cur)
            cur = part
        else:
            cur += part
    lines.append(cur)
    return "<br/>".join(esc(l) for l in lines)


def _doc_text(doc: ResumeDocument) -> str:
    return doc.plain_text()


def _render_once(doc: ResumeDocument, spec: TemplateSpec, options: RenderOptions, density: int,
                 force_single: bool, font_key: str) -> tuple[bytes, RenderInfo]:
    sp_f, m_f, size_delta = DENSITY[density]
    base_body = options.body_size or spec.body_size
    body = max(10.0, base_body + size_delta)
    accent = options.accent if is_hex(options.accent) else spec.accent
    fonts = register(font_key)
    W, H = page_size(options.page_size)
    margin = BASE_MARGIN * m_f
    buf = io.BytesIO()
    info = RenderInfo(density=density, body_size=body, margin_mm=round(margin / mm, 1), font=font_key)
    sections = doc.enabled_sections()
    sidebar = spec.layout == "sidebar" and not force_single
    info.single_column = not sidebar
    title = f"{doc.name} — Resume" if doc.name else "Resume"
    common = dict(pagesize=(W, H), leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
                  title=title, author=doc.name, subject="Resume", creator="CareerRainbow AI")
    st = Styles(spec, fonts, body, sp_f, accent, options.alignment == "justify")
    if not sidebar:
        width = W - 2 * margin
        frame = Frame(margin, margin, width, H - 2 * margin, id="main", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        d = BaseDocTemplate(buf, **common)
        d.addPageTemplates([PageTemplate(id="single", frames=[frame])])
        story = header_flowables(doc, spec, st)
        if spec.heading_style in ("caps_rule", "rule", "bar", "shaded", "accent_text", "underline") and spec.name_align == "left":
            story.append(HRFlowable(width="100%", thickness=1.4 if spec.heading_style != "rule" else 0.8,
                                    color=st.accent, spaceBefore=0, spaceAfter=2 * sp_f))
        info.expected_order = [doc.name]
        for sec in sections:
            story += section_flowables(sec, spec, st, width)
            info.expected_order.append(sec.title)
        d.build(story)
    else:
        content_w = W - 2 * margin
        header_h = 27 * mm
        side_w = content_w * 0.31
        gap = 7 * mm
        main_w = content_w - side_w - gap
        body_h = H - 2 * margin - header_h - 3 * mm
        banner = spec.name_banner
        on_dark_st = Styles(spec, fonts, body, sp_f, accent, options.alignment == "justify", on_dark=banner)
        hdr = Frame(margin, H - margin - header_h, content_w, header_h, id="hdr", leftPadding=0 if not banner else 4 * mm,
                    rightPadding=0, topPadding=2 * mm if banner else 0, bottomPadding=0)
        side = Frame(margin, margin, side_w, body_h, id="side", leftPadding=3 * mm, rightPadding=3 * mm,
                     topPadding=3 * mm, bottomPadding=2 * mm)
        main = Frame(margin + side_w + gap, margin, main_w, body_h, id="main", leftPadding=0, rightPadding=0,
                     topPadding=0, bottomPadding=0)
        later = Frame(margin, margin, content_w, H - 2 * margin, id="later", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        side_bg = tint(accent, 0.9)

        def first_page(canv, _doc):
            canv.saveState()
            canv.setFillColor(colors.HexColor(side_bg))
            canv.rect(margin, margin, side_w, body_h, stroke=0, fill=1)
            if banner:
                canv.setFillColor(colors.HexColor(accent))
                canv.rect(0, H - margin - header_h - 1 * mm, W, margin + header_h + 1 * mm, stroke=0, fill=1)
            else:
                canv.setStrokeColor(colors.HexColor(accent))
                canv.setLineWidth(1.4)
                canv.line(margin, H - margin - header_h + 1 * mm, W - margin, H - margin - header_h + 1 * mm)
            canv.restoreState()

        d = BaseDocTemplate(buf, **common)
        d.addPageTemplates([PageTemplate(id="first", frames=[hdr, side, main], onPage=first_page),
                            PageTemplate(id="later", frames=[later])])
        story = header_flowables(doc, spec, on_dark_st, include_contact=False)
        story.append(FrameBreak())
        info.expected_order = [doc.name]
        side_st = st
        story.append(Paragraph("CONTACT" if spec.heading_style in ("caps_rule", "shaded") else "Contact", side_st.side_h))
        info.expected_order.append("Contact")
        for c in doc.contact_items:
            story.append(Paragraph(wrap_link(c, fonts["regular"], side_st.small.fontSize, side_w - 6 * mm - 2),
                                   side_st.small))
        for sec in sections:
            if sec.sidebar:
                story += section_flowables(sec, spec, side_st, side_w - 6 * mm, side=True)
                info.expected_order.append(sec.title)
        story.append(FrameBreak())
        story.append(NextPageTemplate("later"))
        for sec in sections:
            if not sec.sidebar:
                story += section_flowables(sec, spec, st, main_w)
                info.expected_order.append(sec.title)
        d.build(story)
    info.pages = d.page
    return buf.getvalue(), info


def render_pdf(doc: ResumeDocument, spec: TemplateSpec, options: RenderOptions, *, start_density: int = 0,
               force_single: bool = False) -> tuple[bytes, RenderInfo]:
    """Render, tightening spacing step by step until the page target is met."""
    from src.rendering.fonts import FONTS

    font_key = options.font if options.font in FONTS else spec.font
    font_key, font_note = choose_font(font_key, _doc_text(doc))
    max_pages = None if options.page_target == "academic" else int(options.page_target)
    result = None
    for density in range(start_density, len(DENSITY)):
        pdf, info = _render_once(doc, spec, options, density, force_single, font_key)
        result = (pdf, info)
        if max_pages is None or info.pages <= max_pages:
            break
    pdf, info = result  # type: ignore[misc]
    if font_note:
        info.notes.append(font_note)
    if max_pages is not None and info.pages > max_pages:
        # tightest density did not fit: re-render at normal spacing so the extra page reads well
        pdf, info2 = _render_once(doc, spec, options, start_density, force_single, font_key)
        info2.notes = info.notes
        info = info2
        info.overflow = True
        info.notes.append(f"Content needs {info.pages} pages at a readable size; your target is {max_pages}. "
                          "Nothing was removed — see the fit suggestions.")
    elif info.density:
        info.notes.append("Spacing was tightened slightly to fit the page target."
                          + (f" Body text is {info.body_size:g} pt." if info.body_size < (options.body_size or spec.body_size) else ""))
    return pdf, info
