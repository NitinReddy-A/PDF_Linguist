from __future__ import annotations

import pymupdf
import pytest

from pdf_linguist.translation import TranslationError

PARAGRAPH = (
    "The library will stay open until nine in the evening, and every member may borrow "
    "up to six books at a time during the festival."
)


class FakeTranslator:
    """Deterministic offline translator: tags text so tests can find it in the output."""

    name = "fake"

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[list[str]] = []

    def translate(self, texts, source, target):
        self.calls.append(list(texts))
        if self.fail_on and any(self.fail_on in text for text in texts):
            raise TranslationError("simulated outage")
        return [f"[{target}] {text}" for text in texts]


def make_pdf() -> bytes:
    """A one-page PDF with a heading, a paragraph, a number-only footer and an image."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 80), "Monsoon Reading Festival", fontsize=20, color=(0.05, 0.36, 0.55))
    page.insert_textbox((50, 110, 400, 200), PARAGRAPH, fontsize=11)
    page.insert_text((280, 800), "2026", fontsize=9)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.set_rect(pix.irect, (200, 30, 30))
    page.insert_image((450, 100, 530, 180), pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf()


@pytest.fixture
def fake_translator() -> FakeTranslator:
    return FakeTranslator()
