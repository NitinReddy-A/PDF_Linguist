import pymupdf
import pytest

from pdf_linguist import OCRUnavailableError, TranslateOptions, TranslationError, translate_pdf
from pdf_linguist.translation import RateLimitedError

from .conftest import FakeTranslator


def text_of(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf) as doc:
        return " ".join(" ".join(page.get_text().split()) for page in doc)


def test_translates_in_place_and_keeps_images(sample_pdf, fake_translator):
    pdf, report = translate_pdf(sample_pdf, TranslateOptions(target="fr"), translator=fake_translator)
    text = text_of(pdf)

    assert "[fr] Monsoon Reading Festival" in text
    assert "[fr] The library will stay open" in text
    assert text.count("Monsoon Reading Festival") == 1  # original words were removed, not covered
    assert "2026" in text  # number-only block is left as it was
    with pymupdf.open(stream=pdf) as doc:
        assert len(doc[0].get_images()) == 1
    assert report.translated == 2 and report.failed == 0
    assert report.pages[0].mode == "digital"


def test_translated_text_stays_in_its_box(sample_pdf, fake_translator):
    pdf, _ = translate_pdf(sample_pdf, TranslateOptions(target="fr"), translator=fake_translator)
    with pymupdf.open(stream=pdf) as doc:
        hits = doc[0].search_for("[fr] Monsoon")
    assert hits and 50 <= hits[0].x0 < 60 and 55 <= hits[0].y0 < 85


def test_indic_target_embeds_shaping_font(sample_pdf, fake_translator):
    pdf, report = translate_pdf(sample_pdf, TranslateOptions(target="kn"), translator=fake_translator)
    with pymupdf.open(stream=pdf) as doc:
        fonts = [font[3] for font in doc[0].get_fonts()]
    assert any("Kannada" in font for font in fonts)
    assert report.translated == 2


def test_source_path_and_page_selection(tmp_path, fake_translator):
    doc = pymupdf.open()
    for number in range(1, 4):
        doc.new_page().insert_text((72, 72), f"Chapter {number}")
    path = tmp_path / "book.pdf"
    doc.save(path)

    pdf, report = translate_pdf(path, TranslateOptions(target="de", pages=[3, 1]), translator=fake_translator)
    with pymupdf.open(stream=pdf) as out:
        assert out.page_count == 2
        assert "[de] Chapter 1" in out[0].get_text() and "[de] Chapter 3" in out[1].get_text()
    assert [page.number for page in report.pages] == [1, 3]


def test_out_of_range_pages_are_rejected(sample_pdf, fake_translator):
    with pytest.raises(ValueError, match="out of range"):
        translate_pdf(sample_pdf, TranslateOptions(target="fr", pages=[2]), translator=fake_translator)


def test_rotated_pages_are_handled(fake_translator):
    # A landscape page stored in portrait: content drawn turned, /Rotate 90 makes it read upright.
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((300, 700), "Landscape timetable", rotate=90, fontsize=20)
    page.set_rotation(90)
    pdf, report = translate_pdf(doc.tobytes(), TranslateOptions(target="fr"), translator=fake_translator)
    assert report.translated == 1
    with pymupdf.open(stream=pdf) as out:
        lines = [line for block in out[0].get_text("dict")["blocks"] for line in block.get("lines", [])]
    assert "[fr] Landscape timetable" in text_of(pdf)
    assert all(line["dir"] == (1.0, 0.0) for line in lines)  # translation reads upright too


def test_sideways_text_is_left_alone(fake_translator):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Upright heading", fontsize=14)
    page.insert_text((500, 400), "Vertical margin note", rotate=90)
    pdf, _ = translate_pdf(doc.tobytes(), TranslateOptions(target="fr"), translator=fake_translator)
    assert fake_translator.calls == [["Upright heading"]]
    assert "Vertical margin note" in text_of(pdf)


def test_one_failing_block_keeps_its_original_text(sample_pdf):
    translator = FakeTranslator(fail_on="The library")
    pdf, report = translate_pdf(sample_pdf, TranslateOptions(target="fr"), translator=translator)
    text = text_of(pdf)
    assert "[fr] Monsoon Reading Festival" in text
    assert "The library will stay open" in text and "[fr] The library" not in text
    assert report.translated == 1 and report.failed == 1
    assert any("Kept original text" in warning for warning in report.warnings)


def test_total_failure_raises(sample_pdf):
    with pytest.raises(TranslationError, match="No text could be translated"):
        translate_pdf(sample_pdf, TranslateOptions(target="fr"), translator=FakeTranslator(fail_on=" "))


def test_rate_limit_aborts_the_document(sample_pdf):
    class Limited:
        name = "limited"

        def translate(self, texts, source, target):
            raise RateLimitedError("slow down")

    with pytest.raises(RateLimitedError):
        translate_pdf(sample_pdf, TranslateOptions(target="fr"), translator=Limited())


def test_scanned_page_without_ocr_is_left_unchanged(fake_translator):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False))
    pdf, report = translate_pdf(doc.tobytes(), TranslateOptions(target="kn", ocr="never"), translator=fake_translator)
    assert report.pages[0].mode == "scan (skipped)"
    assert any("OCR is disabled" in warning for warning in report.warnings)
    assert fake_translator.calls == []
    assert pdf


def test_searchable_scan_uses_its_hidden_text_layer(fake_translator):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False))
    page.insert_text((72, 100), "Notice to all students", render_mode=3)  # invisible OCR layer
    pdf, report = translate_pdf(doc.tobytes(), TranslateOptions(target="fr", ocr="never"), translator=fake_translator)
    assert report.pages[0].mode == "searchable scan"
    assert "[fr] Notice to all students" in text_of(pdf)
    with pymupdf.open(stream=pdf) as out:
        drawings = out[0].get_drawings()
    assert any(drawing.get("fill") for drawing in drawings)  # the scanned words were painted over


def test_invalid_options_fail_fast():
    with pytest.raises(ValueError):
        TranslateOptions(target="xx")
    with pytest.raises(ValueError):
        TranslateOptions(target="kn", source="yy")
    with pytest.raises(ValueError, match="ocr must be"):
        TranslateOptions(target="kn", ocr="sometimes")


def test_password_protected_pdf_is_rejected(fake_translator):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    with pytest.raises(ValueError, match="password"):
        translate_pdf(data, TranslateOptions(target="fr"), translator=fake_translator)


def _scanned_page(doc: pymupdf.Document) -> None:
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False))


def test_missing_ocr_skips_scanned_pages_but_translates_the_rest(monkeypatch, fake_translator):
    def no_tesseract(*args, **kwargs):
        raise OCRUnavailableError("Tesseract is not installed")

    monkeypatch.setattr("pdf_linguist.pipeline.ocr_textpage", no_tesseract)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Digital cover page")
    _scanned_page(doc)
    pdf, report = translate_pdf(doc.tobytes(), TranslateOptions(target="fr"), translator=fake_translator)
    assert [page.mode for page in report.pages] == ["digital", "scan (OCR unavailable)"]
    assert "[fr] Digital cover page" in text_of(pdf)
    assert any("Tesseract is not installed" in warning for warning in report.warnings)


def test_missing_ocr_on_a_fully_scanned_document_is_an_error(monkeypatch, fake_translator):
    def no_tesseract(*args, **kwargs):
        raise OCRUnavailableError("Tesseract is not installed")

    monkeypatch.setattr("pdf_linguist.pipeline.ocr_textpage", no_tesseract)
    doc = pymupdf.open()
    _scanned_page(doc)
    with pytest.raises(OCRUnavailableError, match="Tesseract is not installed"):
        translate_pdf(doc.tobytes(), TranslateOptions(target="kn"), translator=fake_translator)


def test_scanned_page_is_ocred_and_painted_over(monkeypatch, fake_translator):
    # Stand in for Tesseract: "recognise" the words by placing them, invisibly, on the page.
    def fake_ocr(page, languages, dpi, tessdata):
        assert languages == "kan+eng"
        page.insert_text((72, 100), "Scanned circular", render_mode=3)
        return page.get_textpage()

    monkeypatch.setattr("pdf_linguist.pipeline.ocr_textpage", fake_ocr)
    doc = pymupdf.open()
    _scanned_page(doc)
    pdf, report = translate_pdf(doc.tobytes(), TranslateOptions(target="en", source="kn"), translator=fake_translator)
    assert report.pages[0].mode == "scan" and report.translated == 1
    assert "[en] Scanned circular" in text_of(pdf)
    with pymupdf.open(stream=pdf) as out:
        assert any(drawing.get("fill") for drawing in out[0].get_drawings())


def test_engines_that_cannot_detect_language_need_a_source(sample_pdf):
    class NeedsSource(FakeTranslator):
        name = "picky"
        requires_source = True

    with pytest.raises(ValueError, match="needs the document language"):
        translate_pdf(sample_pdf, TranslateOptions(target="kn"), translator=NeedsSource())
    _, report = translate_pdf(sample_pdf, TranslateOptions(target="kn", source="en"), translator=NeedsSource())
    assert report.translated == 2
