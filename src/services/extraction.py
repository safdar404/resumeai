"""Text extraction for uploaded resumes (PDF, DOCX, TXT). Works in memory."""
from __future__ import annotations

import io
from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    text: str = ""
    ok: bool = True
    message: str = ""
    pages: int = 0
    warnings: list[str] = field(default_factory=list)


def extract_text(kind: str, data: bytes) -> ExtractionResult:
    if kind == "pdf":
        return _pdf(data)
    if kind == "docx":
        return _docx(data)
    if kind in ("txt", "json"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        return ExtractionResult(text=text.replace("\r\n", "\n"), pages=1)
    return ExtractionResult(ok=False, message=f"Unsupported type: {kind}")


def _pdf(data: bytes) -> ExtractionResult:
    import pymupdf as fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # corrupt file
        return ExtractionResult(ok=False, message=f"Could not open PDF ({type(exc).__name__}).")
    if doc.needs_pass:
        return ExtractionResult(ok=False, message="The PDF is password-protected.")
    texts, image_pages = [], 0
    for page in doc:
        t = page.get_text("text", sort=True)
        texts.append(t)
        if len(t.strip()) < 20 and page.get_images():
            image_pages += 1
    doc_pages = len(texts)
    text = "\n".join(texts).strip()
    if len(text) < 80:
        return ExtractionResult(
            ok=False, pages=doc_pages,
            message="This PDF appears to be scanned (it contains images rather than selectable text). "
                    "OCR is required, which this app does not include. Export your resume as a text-based "
                    "PDF or DOCX, or paste the text into the chat.")
    res = ExtractionResult(text=text, pages=doc_pages)
    if image_pages:
        res.warnings.append(f"{image_pages} page(s) look scanned; their content could not be read.")
    return res


def _docx(data: bytes) -> ExtractionResult:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        return ExtractionResult(ok=False, message=f"Could not open DOCX ({type(exc).__name__}).")
    lines: list[str] = []
    body = doc.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            style = (p.style.name or "").lower() if p.style is not None else ""
            prefix = "• " if "list" in style and p.text.strip() else ""
            lines.append(prefix + p.text)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                seen = []
                for cell in row.cells:
                    if cell.text not in seen:
                        seen.append(cell.text)
                lines.extend(seen)
    warnings = []
    for section in doc.sections:
        for part in (section.header, section.footer):
            t = "\n".join(p.text for p in part.paragraphs if p.text.strip())
            if t:
                lines.insert(0, t)
                warnings.append("Some text was found in the header/footer; it was included at the top.")
    text = "\n".join(lines).strip()
    if not text:
        return ExtractionResult(ok=False, message="No text was found in the DOCX file.")
    return ExtractionResult(text=text, pages=0, warnings=sorted(set(warnings)))
