"""The translation pipeline: PDF in, layout-preserving translated PDF out.

For every page:

1. **Read.** Classify the page as *digital* (real text), *searchable scan*
   (an image with an invisible OCR layer), *scan* (image only) or *legacy-encoded*
   (text in a non-Unicode Indic font). Pick the embedded text or Tesseract OCR
   accordingly, and extract positioned paragraph blocks.
2. **Translate.** Send whole paragraphs to the chosen backend; repeated
   paragraphs are translated once.
3. **Erase.** Redact the original text objects (images and vector art stay
   untouched); on scans, paint over the words with the sampled paper colour.
4. **Render.** Lay each translation into its original box through the HarfBuzz
   HTML engine, shrinking only when the translation is longer than the source.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .config import Settings
from .encoding import has_letters, text_layer_is_broken
from .languages import AUTO, get_language, ocr_languages
from .layout import TextBlock, extract_blocks, image_rects, page_text, widen_blocks
from .ocr import OCRUnavailableError, background_color, is_scanned, ocr_textpage
from .render import BlockRenderer, erase_text, paint_over
from .translation import RateLimitedError, TranslationError, Translator, get_translator

log = logging.getLogger(__name__)

OCR_AUTO, OCR_ALWAYS, OCR_NEVER = "auto", "always", "never"
OCR_MODES = (OCR_AUTO, OCR_ALWAYS, OCR_NEVER)
NO_OCR_MODE = "scan (OCR unavailable)"

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class TranslateOptions:
    target: str
    source: str = AUTO
    translator: str | None = None  # backend name; defaults to PDF_LINGUIST_TRANSLATOR
    ocr: str = OCR_AUTO
    pages: Sequence[int] | None = None  # 1-based page numbers; None = all pages
    settings: Settings = field(default_factory=Settings.from_env)

    def __post_init__(self) -> None:
        get_language(self.target)
        if self.source != AUTO:
            get_language(self.source)
        if self.ocr not in OCR_MODES:
            raise ValueError(f"ocr must be one of {OCR_MODES}, got {self.ocr!r}")


@dataclass
class PageReport:
    number: int
    mode: str  # "digital", "scan", "searchable scan", "broken text layer → OCR", "OCR"
    blocks: int = 0
    translated: int = 0
    failed: int = 0
    shrunk: int = 0  # blocks scaled below 100% to fit their box


@dataclass
class TranslationReport:
    pages: list[PageReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def translated(self) -> int:
        return sum(page.translated for page in self.pages)

    @property
    def failed(self) -> int:
        return sum(page.failed for page in self.pages)


def _has_visible_text(page: pymupdf.Page) -> bool:
    # Text render mode 3 is invisible: the OCR layer of a "searchable" scan.
    return any(span["type"] != 3 and span["opacity"] > 0 for span in page.get_texttrace())


def _translate_blocks(
    translator: Translator, texts: list[str], source: str, target: str, warnings: list[str]
) -> list[str | None]:
    """Translate a page's paragraphs; isolate failures so one bad block never sinks the page."""
    if not texts:
        return []
    try:
        return list(translator.translate(texts, source, target))
    except RateLimitedError:
        raise
    except TranslationError:
        results: list[str | None] = []
        for text in texts:
            try:
                results.append(translator.translate([text], source, target)[0])
            except RateLimitedError:
                raise
            except TranslationError as exc:
                warnings.append(f"Kept original text for {text[:40]!r}…: {exc}")
                results.append(None)
        return results


def _translate_page(
    page: pymupdf.Page,
    number: int,
    options: TranslateOptions,
    translator: Translator,
    renderer: BlockRenderer,
    warnings: list[str],
) -> PageReport:
    if page.rotation:
        page.remove_rotation()  # work in upright coordinates; appearance is unchanged

    text = page_text(page)
    scanned = is_scanned(page, text)
    embedded = bool(text.strip())
    searchable_scan = embedded and not _has_visible_text(page)
    legacy = embedded and text_layer_is_broken(text, options.source)

    use_ocr = options.ocr == OCR_ALWAYS or (options.ocr == OCR_AUTO and (scanned or legacy))
    if scanned and options.ocr == OCR_NEVER:
        warnings.append(f"Page {number} is a scanned image and OCR is disabled; left unchanged.")
        return PageReport(number, "scan (skipped)")

    mode = "digital"
    textpage = None
    if searchable_scan:
        mode = "searchable scan"
    if use_ocr:
        languages = ocr_languages(options.source)
        try:
            textpage = ocr_textpage(page, languages, options.settings.ocr_dpi, options.settings.tessdata)
            mode = "scan" if scanned else ("broken text layer → OCR" if legacy else "OCR")
        except OCRUnavailableError as exc:
            if not embedded:  # nothing else to read: skip this page, keep going with the rest
                warnings.append(f"Page {number} left unchanged: {exc}")
                return PageReport(number, NO_OCR_MODE)
            warnings.append(f"Page {number}: OCR unavailable, used the embedded text layer instead.")
            use_ocr = False
    elif legacy:
        warnings.append(f"Page {number}: text layer looks legacy-encoded or broken, but OCR is disabled.")

    all_blocks = extract_blocks(page, textpage)
    widen_blocks(all_blocks, image_rects(page), rtl=renderer.language.rtl)
    blocks = [block for block in all_blocks if has_letters(block.text)]
    report = PageReport(number, mode, blocks=len(blocks))
    translations = _translate_blocks(translator, [b.text for b in blocks], options.source, options.target, warnings)

    done: list[tuple[TextBlock, str]] = []
    for block, translation in zip(blocks, translations, strict=True):
        if translation and translation.strip():
            done.append((block, translation.strip()))
        else:
            report.failed += 1
    if not done:
        return report

    targets = [block for block, _ in done]
    if embedded:
        erase_text(page, targets)
    if use_ocr or searchable_scan:  # the words are pixels in an image: cover them
        paint_over(page, targets, [background_color(page, block.rect) for block in targets])

    for block, translation in done:
        if renderer.draw(page, block, translation) < 0.999:
            report.shrunk += 1
        report.translated += 1
    return report


def translate_pdf(
    source: bytes | str | Path,
    options: TranslateOptions,
    translator: Translator | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[bytes, TranslationReport]:
    """Translate a PDF and return ``(pdf_bytes, report)``.

    ``source`` is a path or the raw bytes of a PDF. Pass ``translator`` to use a
    custom backend instance (anything with a ``translate(texts, source, target)``
    method); otherwise the backend named in ``options`` is created.
    """
    doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    try:
        if doc.needs_pass:
            raise ValueError("The PDF is password-protected; decrypt it first.")

        numbers = list(range(1, doc.page_count + 1))
        if options.pages:
            invalid = sorted({p for p in options.pages if not 1 <= p <= doc.page_count})
            if invalid:
                raise ValueError(f"Page(s) {invalid} out of range: the document has {doc.page_count} pages.")
            numbers = sorted(set(options.pages))
            doc.select([n - 1 for n in numbers])

        translator = translator or get_translator(options.translator or options.settings.translator)
        if options.source == AUTO and getattr(translator, "requires_source", False):
            raise ValueError(f"The {translator.name} engine needs the document language; it cannot detect it.")
        renderer = BlockRenderer(get_language(options.target))
        report = TranslationReport()

        for index, number in enumerate(numbers):
            if progress:
                progress(index, len(numbers), f"Translating page {number}")
            page_report = _translate_page(doc[index], number, options, translator, renderer, report.warnings)
            report.pages.append(page_report)
            log.info(
                "page %d (%s): %d/%d blocks translated",
                number,
                page_report.mode,
                page_report.translated,
                page_report.blocks,
            )

        if report.translated == 0:
            if any(page.mode == NO_OCR_MODE for page in report.pages):
                raise OCRUnavailableError(next(w for w in report.warnings if "left unchanged" in w))
            if report.failed:
                raise TranslationError("No text could be translated. " + " ".join(report.warnings[-3:]))

        if progress:
            progress(len(numbers), len(numbers), "Embedding fonts")
        try:
            doc.subset_fonts()  # embed only the glyphs actually used
        except Exception as exc:  # pragma: no cover - subsetting is an optimisation only
            report.warnings.append(f"Font subsetting skipped: {exc}")
        return doc.tobytes(garbage=3, deflate=True), report
    finally:
        doc.close()
