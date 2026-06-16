"""PDF and HTML content extraction."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import httpx
import pdfplumber
import structlog

logger = structlog.get_logger(__name__)


def extract_pdf_text(url: str, *, timeout: float = 60.0) -> str:
    """Download PDF and extract text."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.content
    except Exception as exc:
        logger.warning("pdf_download_failed", url=url, error=str(exc))
        return ""

    text_parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception:
        try:
            import fitz  # pymupdf

            doc = fitz.open(stream=data, filetype="pdf")
            for page in doc:
                text_parts.append(page.get_text())
        except Exception as exc2:
            logger.warning("pdf_extract_failed", url=url, error=str(exc2))
            return ""

    return "\n".join(text_parts).strip()
