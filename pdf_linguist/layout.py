"""Layout extraction: turn a PDF page into positioned, styled text blocks.

A block is a paragraph-sized unit of text together with everything needed to put
its translation back in exactly the same place: the bounding box, the dominant
font size, colour, weight and style. Blocks are translated as whole paragraphs
(lines joined, hyphenation removed) so the translator sees complete sentences
instead of line fragments.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pymupdf

from .encoding import normalize

# Ligatures are expanded (no TEXT_PRESERVE_LIGATURES) so "ﬁ" reaches the
# translator as "fi"; words hyphenated across lines are re-joined.
EXTRACT_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP | pymupdf.TEXT_DEHYPHENATE

# PyMuPDF span flag bits.
_ITALIC = 1 << 1
_BOLD = 1 << 4

DEFAULT_FONT_SIZE = 11.0


@dataclass
class TextBlock:
    """A paragraph of text and the visual properties of where it came from."""

    bbox: tuple[float, float, float, float]
    text: str
    font_size: float = DEFAULT_FONT_SIZE
    color: int = 0x000000  # sRGB integer, as reported by PyMuPDF
    bold: bool = False
    italic: bool = False
    # Box the translation may occupy: the original box widened into free space.
    layout_bbox: tuple[float, float, float, float] | None = None

    @property
    def rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(self.bbox)

    @property
    def layout_rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(self.layout_bbox or self.bbox)

    @property
    def hex_color(self) -> str:
        return f"#{self.color & 0xFFFFFF:06x}"


def _is_horizontal(line: dict) -> bool:
    dx, dy = line.get("dir", (1, 0))
    return dx > 0.99 and abs(dy) < 0.01


def _columns(lines: list[dict]) -> list[list[dict]]:
    """Group a block's lines into columns of horizontally overlapping lines.

    MuPDF sometimes reports a table row ("Monday", "Opening ceremony", "10:00 AM")
    as one block of side-by-side lines. Each cell must be translated and placed on
    its own, while the stacked lines of a paragraph or multi-line cell stay together.
    """
    columns: list[tuple[pymupdf.Rect, list[dict]]] = []
    for line in lines:
        box = pymupdf.Rect(line["bbox"])
        for index, (col_box, col_lines) in enumerate(columns):
            if box.x0 < col_box.x1 and box.x1 > col_box.x0:
                col_lines.append(line)
                columns[index] = (col_box | box, col_lines)
                break
        else:
            columns.append((box, [line]))
    return [col_lines for _, col_lines in columns]


def _make_block(lines: list[dict]) -> TextBlock | None:
    spans = [span for line in lines for span in line["spans"] if span["text"].strip()]
    if not spans:
        return None

    text = normalize(" ".join("".join(span["text"] for span in line["spans"]) for line in lines))
    if not text:
        return None

    # The style that covers the most characters represents the block.
    weights: Counter = Counter()
    for span in spans:
        key = (round(span["size"], 1), span["color"], bool(span["flags"] & _BOLD), bool(span["flags"] & _ITALIC))
        weights[key] += len(span["text"].strip())
    (size, color, bold, italic), _ = weights.most_common(1)[0]

    # Union of the kept lines only, so skipped vertical text does not stretch the box.
    rect = pymupdf.Rect()
    for line in lines:
        rect |= pymupdf.Rect(line["bbox"])

    return TextBlock(
        bbox=tuple(rect),
        text=text,
        font_size=size or DEFAULT_FONT_SIZE,
        color=color,
        bold=bold,
        italic=italic,
    )


def extract_blocks(page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> list[TextBlock]:
    """Return the horizontal text blocks of ``page`` in reading order.

    Pass ``textpage`` to read from an OCR text page instead of the embedded text.
    """
    data = page.get_text("dict", flags=EXTRACT_FLAGS, textpage=textpage, sort=True)
    blocks: list[TextBlock] = []
    for raw in data["blocks"]:
        if raw.get("type") != 0:
            continue
        lines = [line for line in raw.get("lines", []) if _is_horizontal(line)]
        for column in _columns(lines):
            block = _make_block(column)
            if block is not None:
                blocks.append(block)
    return blocks


def image_rects(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Bounding boxes of the images on ``page``, ignoring full-page scan backgrounds."""
    half_page = abs(page.rect) / 2
    rects = (pymupdf.Rect(info["bbox"]) for info in page.get_image_info())
    return [rect for rect in rects if not rect.is_empty and abs(rect) < half_page]


def widen_blocks(blocks: list[TextBlock], obstacles: list[pymupdf.Rect], rtl: bool = False, gap: float = 4.0) -> None:
    """Let each block grow sideways into empty space before its translation is laid out.

    Translations are usually longer than their source, and the extracted box hugs
    the source words tightly: a heading's box is exactly as wide as the English
    heading. Growing the box (rightwards, or leftwards for right-to-left targets)
    until the next text block, image or the edge of the text column lets the
    translation keep its original font size instead of being shrunk.
    """
    if not blocks:
        return
    rects = [block.rect for block in blocks]
    column_left = min(rect.x0 for rect in rects)
    column_right = max(rect.x1 for rect in rects)
    for block, rect in zip(blocks, rects, strict=True):
        others = [o for o in rects + obstacles if o is not rect and o.y0 < rect.y1 and o.y1 > rect.y0]
        if rtl:
            edges = [o.x1 + gap for o in others if o.x1 <= rect.x0 + 1]
            left = max([column_left, *edges])
            block.layout_bbox = (min(left, rect.x0), rect.y0, rect.x1, rect.y1)
        else:
            edges = [o.x0 - gap for o in others if o.x0 >= rect.x1 - 1]
            right = min([column_right, *edges])
            block.layout_bbox = (rect.x0, rect.y0, max(right, rect.x1), rect.y1)


def page_text(page: pymupdf.Page) -> str:
    """All embedded text on ``page`` (empty for image-only scans)."""
    return page.get_text("text", flags=EXTRACT_FLAGS)
