"""Generate ``examples/sample.pdf``: a one-page English notice to try PDF Linguist on.

The page deliberately mixes the things that break naive translators: a coloured
title banner, headings, multi-line paragraphs, a tinted call-out box, a ruled
table and a footer.

    python examples/generate_sample.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

OUT = Path(__file__).with_name("sample.pdf")
INK, ACCENT, TINT = (0.13, 0.13, 0.15), (0.05, 0.36, 0.55), (0.91, 0.95, 0.98)


def text(page: pymupdf.Page, rect: tuple, html: str, size: float = 11, color: str = "#222226", bold=False) -> None:
    css = f"* {{font-family: sans-serif; font-size: {size}px; color: {color}; line-height: 1.35; margin: 0;}}"
    if bold:
        css += " * {font-weight: bold;}"
    page.insert_htmlbox(rect, html, css=css)


def build() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4

    page.draw_rect((0, 0, 595, 96), color=None, fill=ACCENT)
    text(page, (48, 30, 547, 62), "Riverside Community Library", size=24, color="#ffffff", bold=True)
    text(page, (48, 64, 547, 84), "Public notice · Monsoon Reading Festival", size=11, color="#d6e6f2")

    text(page, (48, 122, 547, 146), "Dear readers,", size=13, bold=True)
    text(
        page,
        (48, 150, 547, 230),
        "We are delighted to announce our annual Monsoon Reading Festival. For two weeks the library "
        "will stay open until nine in the evening, and every member may borrow up to six books at a "
        "time. Story sessions for children will be held every Saturday morning in the reading hall.",
    )

    page.draw_rect((48, 240, 547, 312), color=None, fill=TINT)
    page.draw_rect((48, 240, 52, 312), color=None, fill=ACCENT)
    text(page, (64, 250, 535, 268), "Please note", size=12, color="#0d5c8c", bold=True)
    text(
        page,
        (64, 270, 535, 306),
        "Books borrowed during the festival must be returned within twenty-one days. "
        "Late returns will not be charged a fine this year.",
    )

    text(page, (48, 332, 547, 352), "Festival schedule", size=13, bold=True)
    rows = [
        ("Day", "Event", "Time"),
        ("Monday", "Opening ceremony and book fair", "10:00 AM"),
        ("Wednesday", "Meet the author", "4:00 PM"),
        ("Saturday", "Storytelling for children", "9:30 AM"),
        ("Sunday", "Poetry evening and prize distribution", "6:00 PM"),
    ]
    cols, top, height = (48, 160, 440, 547), 360, 28
    for r, row in enumerate(rows):
        y = top + r * height
        if r == 0:
            page.draw_rect((48, y, 547, y + height), color=None, fill=TINT)
        for c, cell in enumerate(row):
            text(page, (cols[c] + 8, y + 7, cols[c + 1] - 8, y + height - 2), cell, size=10.5, bold=r == 0)
        page.draw_line((48, y + height), (547, y + height), color=(0.75, 0.78, 0.82), width=0.6)

    text(
        page,
        (48, 520, 547, 580),
        "Everyone is welcome. Entry to all events is free, and no registration is required. "
        "For any questions, please speak to the staff at the front desk.",
    )
    text(page, (360, 600, 547, 640), "Head Librarian<br>Riverside Community Library", size=10.5, bold=True)

    page.draw_line((48, 790), (547, 790), color=INK, width=0.4)
    text(page, (48, 796, 547, 812), "Riverside Community Library · Open daily 8 AM – 9 PM", size=8.5, color="#6b6b75")

    doc.subset_fonts()
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


if __name__ == "__main__":
    OUT.write_bytes(build())
    print(f"Wrote {OUT}")
