"""Runtime configuration, read from environment variables (and an optional ``.env``).

Nothing secret is required to run PDF Linguist. See ``.env.example`` for the
variables that tune it.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional: a missing package or .env file is not an error.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    # Only the working directory's .env: never pick up unrelated files from parent folders.
    with contextlib.suppress(OSError, UnicodeDecodeError):  # unreadable .env: use the real environment
        load_dotenv(Path.cwd() / ".env")


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    try:
        return int(value) if value else default
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got {value!r}") from None


@dataclass(frozen=True)
class Settings:
    translator: str = "google"
    ocr_dpi: int = 300
    tessdata: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            translator=os.getenv("PDF_LINGUIST_TRANSLATOR", "google").strip() or "google",
            ocr_dpi=_int("PDF_LINGUIST_OCR_DPI", 300),
            tessdata=os.getenv("TESSDATA_PREFIX") or None,
        )
