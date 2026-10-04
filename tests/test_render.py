import pymupdf

from pdf_linguist.languages import get_language
from pdf_linguist.layout import TextBlock
from pdf_linguist.render import FONTS_DIR, BlockRenderer, find_font


def test_bundled_kannada_font_is_found():
    font = find_font("Kannada")
    assert font is not None and font.parent == FONTS_DIR
    assert find_font("Kannada", FONTS_DIR / "missing") is None


def test_html_is_escaped():
    renderer = BlockRenderer(get_language("hi"))
    assert renderer.html("a < b & c\nd") == '<div dir="ltr">a &lt; b &amp; c<br>d</div>'


def test_css_carries_block_style():
    renderer = BlockRenderer(get_language("kn"))
    css = renderer.css(TextBlock((0, 0, 10, 10), "x", font_size=14, color=0x0D5C8C, bold=True, italic=True))
    assert "@font-face" in css and "pl-Kannada" in css
    assert "font-size: 14.00px" in css and "color: #0d5c8c" in css
    assert "font-weight: bold" in css and "font-style: italic" in css


def test_rtl_languages_are_right_aligned():
    renderer = BlockRenderer(get_language("ur"))
    assert 'dir="rtl"' in renderer.html("x")
    assert "text-align: right" in renderer.css(TextBlock((0, 0, 1, 1), "x"))


def test_draw_shapes_kannada_with_bundled_font():
    doc = pymupdf.open()
    page = doc.new_page()
    block = TextBlock((50, 50, 300, 100), "x", font_size=12)
    scale = BlockRenderer(get_language("kn")).draw(page, block, "ಕನ್ನಡ ಕ್ಷೇತ್ರ")
    assert scale == 1.0
    assert any("Kannada" in font[3] for font in page.get_fonts())


def test_draw_shrinks_long_text_to_fit():
    doc = pymupdf.open()
    page = doc.new_page()
    block = TextBlock((50, 50, 150, 64), "x", font_size=12)
    scale = BlockRenderer(get_language("hi")).draw(page, block, "बहुत लंबा अनुवाद " * 20)
    assert 0 < scale < 1
