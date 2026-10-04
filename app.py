"""PDF Linguist web app.  Run with:  streamlit run app.py"""

from __future__ import annotations

import argparse
import hashlib

import pymupdf
import streamlit as st

from pdf_linguist import (
    AUTO,
    LANGUAGES,
    OCRUnavailableError,
    TranslateOptions,
    TranslationError,
    __version__,
    get_language,
    translate_pdf,
)
from pdf_linguist.cli import parse_pages

st.set_page_config(page_title="PDF Linguist", page_icon="🌐", layout="wide")

st.markdown(
    """
    <style>
      .pl-hero h1 { font-size: 2.6rem; margin-bottom: 0; letter-spacing: -0.02em; }
      .pl-hero p  { font-size: 1.1rem; opacity: 0.75; margin-top: 0.25rem; }
      .pl-scripts { font-size: 1.35rem; letter-spacing: 0.08em; opacity: 0.9; }
    </style>
    <div class="pl-hero">
      <h1>PDF Linguist</h1>
      <p>Translate any PDF, digital or scanned, without breaking its layout or its script.</p>
      <div class="pl-scripts">ಕನ್ನಡ · हिन्दी · தமிழ் · తెలుగు · മലയാളം · বাংলা · ગુજરાતી · ਪੰਜਾਬੀ · ଓଡ଼ିଆ · اردو</div>
    </div>
    """,
    unsafe_allow_html=True,
)

CODES = [language.code for language in LANGUAGES]
ENGINES = {"google": "Google Translate (online)", "indictrans": "IndicTrans2 by AI4Bharat (offline)"}
OCR_LABELS = {"auto": "Auto: scans & broken text", "always": "Always", "never": "Never"}


def language_label(code: str) -> str:
    return "Detect automatically" if code == AUTO else get_language(code).label


@st.cache_data(show_spinner=False, max_entries=64)
def render_page(pdf: bytes, index: int, dpi: int = 110) -> bytes:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc[index].get_pixmap(dpi=dpi).tobytes("png")


@st.cache_data(show_spinner=False, max_entries=16)
def page_count(pdf: bytes) -> int:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc.page_count


with st.sidebar:
    st.header("Translation")
    target = st.selectbox("Translate to", CODES, index=CODES.index("kn"), format_func=language_label)
    source = st.selectbox("Document language", [AUTO, *CODES], format_func=language_label)
    engine = st.selectbox("Engine", list(ENGINES), format_func=ENGINES.get)
    st.header("Pages & OCR")
    pages_spec = st.text_input("Pages", placeholder="All pages (or e.g. 1-3, 5)")
    ocr = st.radio("OCR", list(OCR_LABELS), format_func=OCR_LABELS.get, horizontal=False)
    st.caption(
        "OCR runs on scanned pages and on pages whose text layer uses legacy, non-Unicode "
        "Indic fonts (Nudi, Baraha, Kruti Dev…). Choose the document language for best OCR."
    )
    st.divider()
    st.caption(f"PDF Linguist v{__version__} · MIT License")

upload = st.file_uploader("Upload a PDF", type=["pdf"])
if upload is None:
    st.info(
        "Upload a PDF to begin. Text is re-typeset in place, so headings, columns, "
        "colours and images stay where they were."
    )
    st.stop()

pdf_bytes = upload.getvalue()
try:
    total_pages = page_count(pdf_bytes)
except Exception as exc:  # corrupt or non-PDF upload
    st.error(f"Could not open this PDF: {exc}")
    st.stop()

try:
    pages = parse_pages(pages_spec) if pages_spec.strip() else None
except argparse.ArgumentTypeError as exc:
    st.error(f"Pages: {exc}")
    st.stop()

job_key = hashlib.sha256(pdf_bytes).hexdigest() + repr((target, source, engine, ocr, pages))
result = st.session_state.get("result")
if result and result["key"] != job_key:
    result = None

if st.button(f"Translate to {get_language(target).name}", type="primary", use_container_width=True):
    bar = st.progress(0.0, text="Starting…")

    def on_progress(done: int, total: int, message: str) -> None:
        bar.progress(done / total if total else 1.0, text=message)

    try:
        options = TranslateOptions(target=target, source=source, translator=engine, ocr=ocr, pages=pages)
        output, report = translate_pdf(pdf_bytes, options, progress=on_progress)
    except (ValueError, TranslationError, OCRUnavailableError) as exc:
        bar.empty()
        st.error(str(exc))
        st.stop()
    bar.empty()
    result = {"key": job_key, "pdf": output, "report": report, "pages": pages or list(range(1, total_pages + 1))}
    st.session_state["result"] = result

shown_pages = result["pages"] if result else list(range(1, total_pages + 1))
page_number = shown_pages[0]
if len(shown_pages) > 1:
    page_number = st.select_slider("Page", options=shown_pages)

original, translated = st.columns(2, gap="large")
with original:
    st.subheader("Original")
    st.image(render_page(pdf_bytes, page_number - 1), use_container_width=True)
with translated:
    st.subheader(get_language(target).label)
    if result:
        st.image(render_page(result["pdf"], shown_pages.index(page_number)), use_container_width=True)
    else:
        st.caption("Your translated page will appear here.")

if result:
    report = result["report"]
    stats = st.columns(4)
    stats[0].metric("Pages", len(report.pages))
    stats[1].metric("Paragraphs translated", report.translated)
    stats[2].metric("Fitted to box", sum(page.shrunk for page in report.pages))
    stats[3].metric("Kept original", report.failed)
    st.download_button(
        "Download translated PDF",
        data=result["pdf"],
        file_name=f"{upload.name.rsplit('.', 1)[0]}.{target}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    with st.expander("Page details"):
        st.table(
            [
                {
                    "Page": p.number,
                    "Read as": p.mode,
                    "Paragraphs": p.blocks,
                    "Translated": p.translated,
                    "Shrunk to fit": p.shrunk,
                }
                for p in report.pages
            ]
        )
    for warning in report.warnings:
        st.warning(warning)
