import pymupdf

from pdf_linguist.layout import TextBlock, extract_blocks, image_rects, widen_blocks


def test_extracts_paragraph_with_style(sample_pdf):
    page = pymupdf.open(stream=sample_pdf)[0]
    blocks = extract_blocks(page)
    texts = [block.text for block in blocks]

    assert "Monsoon Reading Festival" in texts
    paragraph = next(block for block in blocks if block.text.startswith("The library"))
    assert "\n" not in paragraph.text  # lines joined into one paragraph
    assert paragraph.text.endswith("during the festival.")
    assert round(paragraph.font_size) == 11

    heading = next(block for block in blocks if block.text == "Monsoon Reading Festival")
    assert round(heading.font_size) == 20
    assert heading.hex_color == "#0d5c8c"


def test_side_by_side_lines_become_separate_cells():
    doc = pymupdf.open()
    page = doc.new_page()
    css = "* {font-size: 11px;}"
    for x, cell in ((50, "Monday"), (170, "Opening ceremony"), (450, "10:00 AM")):
        page.insert_htmlbox((x, 100, x + 110, 120), cell, css=css)
    texts = sorted(block.text for block in extract_blocks(page))
    assert texts == ["10:00 AM", "Monday", "Opening ceremony"]


def test_image_rects_skip_full_page_scans(sample_pdf):
    page = pymupdf.open(stream=sample_pdf)[0]
    assert len(image_rects(page)) == 1
    page.insert_image(page.rect, pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False))
    assert len(image_rects(page)) == 1


def test_widen_stops_at_neighbours_and_column_edge():
    heading = TextBlock((50, 50, 120, 70), "Title")
    paragraph = TextBlock((50, 80, 500, 120), "Body")
    left_cell = TextBlock((50, 130, 90, 145), "Day")
    right_cell = TextBlock((170, 130, 260, 145), "Event")
    blocks = [heading, paragraph, left_cell, right_cell]
    widen_blocks(blocks, obstacles=[])

    assert heading.layout_rect.x1 == 500  # grows to the text column's right edge
    assert left_cell.layout_rect.x1 == 166  # stops a gap before the next cell
    assert right_cell.layout_rect.x1 == 500
    assert heading.rect.x1 == 120  # original box (used for erasing) is untouched


def test_widen_respects_images_and_rtl():
    block = TextBlock((50, 50, 120, 70), "Caption")
    other = TextBlock((50, 100, 500, 120), "Body")
    widen_blocks([block, other], obstacles=[pymupdf.Rect(300, 40, 400, 90)])
    assert block.layout_rect.x1 == 296

    rtl_block = TextBlock((400, 50, 500, 70), "Caption")
    widen_blocks([rtl_block, TextBlock((50, 100, 500, 120), "Body")], obstacles=[], rtl=True)
    assert rtl_block.layout_rect.x0 == 50
