"""Local ingestion; no network access. Page text is the evidence coordinate system."""

import hashlib
import shutil
import subprocess
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pypdf import PdfReader

from .models import Issue

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 50
MAX_CHARS = 200_000


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    source: Literal["text", "pdf", "ocr"]


@dataclass(frozen=True)
class Document:
    sha256: str
    pages: list[Page]
    issues: list[Issue]


def ocr_page(path: Path, index: int) -> str:
    if not shutil.which("tesseract"):
        raise InputError("OCR requires Tesseract on PATH and the [ocr] installation extra")
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise InputError("Install change-order-extractor[ocr] to render scanned pages") from exc
    with tempfile.TemporaryDirectory(prefix="change-order-") as directory:
        with pdfium.PdfDocument(path) as pdf:
            with closing(pdf[index]) as page:
                # Bound render allocation before creating a bitmap (300 DPI, <=25M pixels).
                width, height = page.get_size()
                scale = min(300 / 72, (25_000_000 / max(width * height, 1)) ** 0.5)
                bitmap = page.render(scale=scale)
                try:
                    bitmap.to_pil().save(Path(directory) / "page.png")
                finally:
                    bitmap.close()
        try:
            result = subprocess.run(
                ["tesseract", str(Path(directory) / "page.png"), "stdout", "-l", "eng"],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise InputError("Tesseract failed or exceeded its 60-second page timeout") from exc
        return result.stdout


def read_document(path: Path, ocr: Literal["off", "auto", "always"] = "off") -> Document:
    if ocr not in {"off", "auto", "always"}:
        raise InputError("OCR mode must be off, auto, or always")
    if path.stat().st_size > MAX_BYTES:
        raise InputError("Input exceeds 20 MiB")
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    issues: list[Issue] = []
    pages: list[Page] = []
    if path.suffix.lower() in {".txt", ".md"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError("Text input must be UTF-8") from exc
        pages = [Page(i + 1, t, "text") for i, t in enumerate(text.split("\f"))]
    elif path.suffix.lower() == ".pdf":
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise InputError("Encrypted PDFs are not supported; provide a decrypted copy")
            if len(reader.pages) > MAX_PAGES:
                raise InputError("Input exceeds 50 pages")
            for index, page in enumerate(reader.pages):
                text = page.extract_text(extraction_mode="layout") or ""
                source = "pdf"
                sparse = len("".join(text.split())) < 40
                if ocr == "always" or (ocr == "auto" and sparse):
                    text = ocr_page(path, index)
                    source = "ocr"
                if sparse and ocr == "off":
                    issues.append(
                        Issue(code="sparse_page", message=f"Page {index + 1} may need OCR")
                    )
                pages.append(Page(index + 1, text, source))
        except InputError:
            raise
        except Exception as exc:
            raise InputError("Unable to read PDF") from exc
    else:
        raise InputError("Supported inputs: .pdf, .txt, .md")
    pages = [
        Page(p.number, p.text.replace("\r\n", "\n").replace("\r", "\n"), p.source) for p in pages
    ]
    if len(pages) > MAX_PAGES or sum(len(p.text) for p in pages) > MAX_CHARS:
        raise InputError("Input exceeds 50 pages or 200,000 extracted characters")
    if not pages or not any(p.text.strip() for p in pages):
        raise InputError("No readable text; use --ocr auto for scanned PDFs")
    return Document(digest, pages, issues)
