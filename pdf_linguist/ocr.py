"""OCR for scanned pages and pages with broken text layers.

OCR runs through PyMuPDF's built-in Tesseract integration, so recognised words
come back with exact page coordinates in the same structure as embedded text.
Scanned and digital pages then flow through one identical layout pipeline.
"""

from __future__ import annotations

import pymupdf

from .layout import EXTRACT_FLAGS


class OCRUnavailableError(RuntimeError):
    """Raised when Tesseract or the requested language data is not installed."""


def is_scanned(page: pymupdf.Page, text: str) -> bool:
    """A page is a scan when it has images but no embedded text."""
    return not text.strip() and bool(page.get_images())


def ocr_textpage(page: pymupdf.Page, languages: str, dpi: int = 300, tessdata: str | None = None) -> pymupdf.TextPage:
    """Run Tesseract over the full rendered page and return a positioned text page."""
    try:
        return page.get_textpage_ocr(flags=EXTRACT_FLAGS, language=languages, dpi=dpi, full=True, tessdata=tessdata)
    except Exception as exc:  # PyMuPDF raises bare RuntimeError/ValueError here.
        raise OCRUnavailableError(
            f"OCR failed for languages {languages!r}: {exc}. Install Tesseract with the "
            "matching language packs and set TESSDATA_PREFIX to its tessdata folder."
        ) from exc


def background_color(page: pymupdf.Page, rect: pymupdf.Rect) -> tuple[float, float, float]:
    """Estimate the paper colour behind ``rect`` (per-channel median of its pixels).

    Ink usually covers well under half of a text box, so the median lands on the
    paper tone. Used to paint over scanned text without leaving white patches on
    off-white or tinted scans.
    """
    clip = rect & page.rect
    if clip.is_empty:
        return (1.0, 1.0, 1.0)
    pix = page.get_pixmap(clip=clip, dpi=72, colorspace=pymupdf.csRGB, alpha=False)
    pixels = pix.width * pix.height
    if not pixels:
        return (1.0, 1.0, 1.0)
    samples = pix.samples
    channels = []
    for channel in range(3):
        values = sorted(samples[channel::3])
        channels.append(values[len(values) // 2] / 255)
    return (channels[0], channels[1], channels[2])
