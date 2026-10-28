"""Upload validation: extension, size and file signature (magic bytes)."""
from __future__ import annotations

import zipfile
import io
from dataclasses import dataclass

from src.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES


@dataclass
class UploadCheck:
    ok: bool
    kind: str = ""
    message: str = ""


def check_upload(filename: str, data: bytes) -> UploadCheck:
    name = (filename or "").lower()
    ext = next((e for e in ALLOWED_UPLOAD_EXTENSIONS if name.endswith(e)), None)
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".heic", ".webp")):
        return UploadCheck(False, "image", "Image resumes need OCR, which this app does not include. "
                           "Please upload a text-based PDF, DOCX or TXT file instead.")
    if not ext:
        return UploadCheck(False, "", "Unsupported file type. Use PDF, DOCX, TXT or a CareerRainbow JSON profile.")
    if len(data) == 0:
        return UploadCheck(False, ext, "The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        return UploadCheck(False, ext, f"The file is larger than {MAX_UPLOAD_BYTES // (1024*1024)} MB.")
    if ext == ".pdf" and not data[:1024].lstrip().startswith(b"%PDF"):
        return UploadCheck(False, ext, "This file does not look like a valid PDF.")
    if ext == ".docx":
        if not data.startswith(b"PK"):
            return UploadCheck(False, ext, "This file does not look like a valid DOCX document.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if "word/document.xml" not in names:
                    return UploadCheck(False, ext, "The DOCX file has no document body.")
                if sum(i.file_size for i in z.infolist()) > 60 * MAX_UPLOAD_BYTES:
                    return UploadCheck(False, ext, "The DOCX file expands to an unsafe size.")
        except zipfile.BadZipFile:
            return UploadCheck(False, ext, "The DOCX file is damaged.")
    if ext in (".txt", ".json"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                data.decode("cp1252")
            except UnicodeDecodeError:
                return UploadCheck(False, ext, "The text file encoding is not supported (use UTF-8).")
    return UploadCheck(True, ext.lstrip("."), "")
