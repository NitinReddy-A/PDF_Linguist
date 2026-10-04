"""Command-line interface: ``pdf-linguist input.pdf --to kn``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .languages import AUTO, LANGUAGES
from .ocr import OCRUnavailableError
from .pipeline import OCR_MODES, TranslateOptions, translate_pdf
from .translation import BACKENDS, TranslationError


def parse_pages(spec: str) -> list[int]:
    """Parse a page selection such as ``"1-3,5"`` into ``[1, 2, 3, 5]``."""
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start, end = (int(value) for value in part.split("-", 1))
                if start > end:
                    raise ValueError
                pages.update(range(start, end + 1))
            else:
                pages.add(int(part))
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid page range {part!r} (use e.g. 1-3,5)") from None
    if not pages or min(pages) < 1:
        raise argparse.ArgumentTypeError("pages are numbered from 1")
    return sorted(pages)


def build_parser() -> argparse.ArgumentParser:
    codes = ", ".join(language.code for language in LANGUAGES)
    parser = argparse.ArgumentParser(
        prog="pdf-linguist",
        description="Translate a PDF while keeping its layout, built for Indian scripts.",
        epilog=f"Language codes: {codes}",
    )
    parser.add_argument("input", type=Path, help="PDF to translate (digital or scanned)")
    parser.add_argument("-t", "--to", dest="target", required=True, metavar="LANG", help="target language, e.g. kn")
    parser.add_argument("-s", "--from", dest="source", default=AUTO, metavar="LANG", help="source language or auto")
    parser.add_argument("-o", "--output", type=Path, help="output path (default: <input>.<LANG>.pdf)")
    parser.add_argument("-e", "--engine", choices=sorted(BACKENDS), help="translation backend (default: google)")
    parser.add_argument("--ocr", choices=OCR_MODES, default="auto", help="when to OCR pages (default: auto)")
    parser.add_argument("-p", "--pages", type=parse_pages, help="pages to translate, e.g. 1-3,5")
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress per page")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Indic text in messages must not crash legacy consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    if not args.input.is_file():
        print(f"error: {args.input} does not exist", file=sys.stderr)
        return 2
    output = args.output or args.input.with_name(f"{args.input.stem}.{args.target}.pdf")

    try:
        options = TranslateOptions(
            target=args.target, source=args.source, translator=args.engine, ocr=args.ocr, pages=args.pages
        )

        def progress(done: int, total: int, message: str) -> None:
            print(f"[{done}/{total}] {message}", file=sys.stderr)

        pdf, report = translate_pdf(args.input, options, progress=progress)
    except (ValueError, TranslationError, OCRUnavailableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output.write_bytes(pdf)
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"Translated {report.translated} blocks on {len(report.pages)} page(s) -> {output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
