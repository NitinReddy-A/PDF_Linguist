"""PDF Linguist: layout-preserving PDF translation, built for Indian scripts.

Quick start::

    from pdf_linguist import TranslateOptions, translate_pdf

    pdf_bytes, report = translate_pdf("circular.pdf", TranslateOptions(target="kn"))
    open("circular.kn.pdf", "wb").write(pdf_bytes)
"""

from .languages import AUTO, LANGUAGES, Language, get_language
from .ocr import OCRUnavailableError
from .pipeline import OCR_MODES, PageReport, TranslateOptions, TranslationReport, translate_pdf
from .translation import TranslationError, get_translator

__version__ = "2.0.0"

__all__ = [
    "AUTO",
    "LANGUAGES",
    "OCR_MODES",
    "Language",
    "OCRUnavailableError",
    "PageReport",
    "TranslateOptions",
    "TranslationError",
    "TranslationReport",
    "__version__",
    "get_language",
    "get_translator",
    "translate_pdf",
]
