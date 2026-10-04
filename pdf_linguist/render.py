"""Rendering translated text back onto the page.

This is where Indian scripts are won or lost.

Classic PDF text APIs (``insert_text`` / ``insert_textbox``, FPDF, ReportLab's
canvas, ...) map one Unicode code point to one glyph and lay glyphs out left to
right. That is fine for English and fatal for Indic scripts, whose visual form
is not their stored order: Devanagari "कि" is stored as क + ि but the vowel
sign is *drawn* first; Kannada "ಕ್ಷ" is three code points that become a single
conjunct glyph; reph, below-base and post-base forms all need re-ordering and
glyph substitution from the font's OpenType tables.

PDF Linguist never places glyphs itself. Each translated block is written as a
tiny HTML document and laid out by MuPDF's HTML/CSS engine
(``Page.insert_htmlbox``), which shapes every run with **HarfBuzz**, the same
shaping engine used by Chrome, Firefox and Android. That gives:

* correct conjuncts, matras, reph and ligatures for every Indic script;
* right-to-left layout for Urdu and Arabic;
* automatic font fallback to MuPDF's built-in Noto families for any script that
  has no bundled font;
* fit-to-box layout: text is wrapped inside the original bounding box and scaled
  down only as much as needed, so the page geometry is preserved even when the
  translation is longer than the source.
"""

from __future__ import annotations

import html
from pathlib import Path

import pymupdf

from .languages import Language
from .layout import TextBlock

FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# Slightly taller lines than Latin defaults: Indic scripts stack vowel signs
# above and below the base consonant.
LINE_HEIGHT = 1.2


def find_font(script: str, fonts_dir: Path = FONTS_DIR) -> Path | None:
    """Return a bundled ``NotoSans<Script>*.ttf``/``.otf`` font for ``script``, if any."""
    if not fonts_dir.is_dir():
        return None
    matches = sorted(path for path in fonts_dir.glob(f"NotoSans{script}*") if path.suffix.lower() in {".ttf", ".otf"})
    return matches[0] if matches else None


class BlockRenderer:
    """Writes translated blocks for one target language onto PDF pages."""

    def __init__(self, language: Language, fonts_dir: Path = FONTS_DIR) -> None:
        self.language = language
        font = find_font(language.script, fonts_dir)
        self.archive = pymupdf.Archive(str(font.parent)) if font else None
        self.font_face = (
            f'@font-face {{font-family: "pl-{language.script}"; src: url("{font.name}");}}\n' if font else ""
        )
        # Bundled font first, then MuPDF's built-in Noto fallbacks.
        self.font_family = f'"pl-{language.script}", sans-serif' if font else "sans-serif"

    def css(self, block: TextBlock) -> str:
        rules = [
            f"font-family: {self.font_family}",
            f"font-size: {block.font_size:.2f}px",
            f"color: {block.hex_color}",
            f"line-height: {LINE_HEIGHT}",
            "margin: 0",
            "padding: 0",
        ]
        if block.bold:
            rules.append("font-weight: bold")
        if block.italic:
            rules.append("font-style: italic")
        if self.language.rtl:
            rules.append("text-align: right")
        return f"{self.font_face}* {{{'; '.join(rules)};}}"

    def html(self, text: str) -> str:
        body = html.escape(text).replace("\n", "<br>")
        direction = "rtl" if self.language.rtl else "ltr"
        return f'<div dir="{direction}">{body}</div>'

    def draw(self, page: pymupdf.Page, block: TextBlock, text: str) -> float:
        """Lay ``text`` out in ``block``'s layout box. Returns the applied scale (1.0 = no shrink)."""
        _, scale = page.insert_htmlbox(
            block.layout_rect,
            self.html(text),
            css=self.css(block),
            archive=self.archive,
            scale_low=0,  # shrink as far as needed: never overflow the original box
        )
        return scale


def erase_text(page: pymupdf.Page, blocks: list[TextBlock]) -> None:
    """Remove the original text under ``blocks`` but keep images and vector art.

    Redaction deletes the text objects themselves (not just covers them), so the
    original words are gone from the output's text layer and cannot be selected,
    searched or copied behind the translation.
    """
    for block in blocks:
        page.add_redact_annot(block.rect, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)


def paint_over(page: pymupdf.Page, blocks: list[TextBlock], colors: list[tuple[float, float, float]]) -> None:
    """Cover text that is part of a scanned image with the surrounding paper colour."""
    for block, color in zip(blocks, colors, strict=True):
        page.draw_rect(block.rect, color=None, fill=color, overlay=True)
