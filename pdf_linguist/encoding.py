"""Unicode hygiene for Indian-language text.

Two things go wrong with Indic text inside PDFs far more often than with Latin
text, and generic translators silently ignore both:

1. **Normalisation.** The same syllable can be stored as different code-point
   sequences (precomposed vs. nukta + base). Text is normalised to NFC before it
   is translated so the translator sees one canonical spelling. Zero-width
   joiners (ZWJ/ZWNJ) are kept: in Indic scripts they change how a conjunct is
   drawn.
2. **Broken text layers.** Many Indian PDFs were typeset with legacy, non-Unicode
   fonts (Nudi and Baraha for Kannada, Kruti Dev for Hindi, ...). Their text layer
   *looks* like Latin gibberish or private-use code points even though the page
   renders perfectly. Translating that text produces garbage, so such pages are
   detected here and re-read through OCR instead.
"""

from __future__ import annotations

import unicodedata

from .languages import AUTO, SCRIPTS, get_language

REPLACEMENT_CHAR = "�"

# Share of letters that must be in the expected script for a text layer to be
# trusted when the source language is known. Kept low so that bilingual pages
# (Kannada body, English codes and names) pass; legacy-font layers score ~0.
MIN_SCRIPT_SHARE = 0.2
# Share of unreadable characters (U+FFFD or private-use code points) above which
# a text layer is treated as broken regardless of language.
MAX_UNREADABLE_SHARE = 0.1
# Below this many letters there is not enough evidence to judge a page.
MIN_LETTERS = 20


def normalize(text: str) -> str:
    """NFC-normalise ``text`` and collapse runs of whitespace into single spaces."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def is_private_use(char: str) -> bool:
    return unicodedata.category(char) == "Co"


def has_letters(text: str) -> bool:
    """True if ``text`` contains at least one letter in any script."""
    return any(char.isalpha() for char in text)


def script_share(text: str, script_name: str) -> float:
    """Fraction of the letters in ``text`` that belong to ``script_name``."""
    script = SCRIPTS[script_name]
    letters = [char for char in text if char.isalpha() or is_private_use(char)]
    if not letters:
        return 0.0
    return sum(script.contains(char) for char in letters) / len(letters)


def unreadable_share(text: str) -> float:
    """Fraction of non-space characters that cannot be read (U+FFFD, private use)."""
    chars = [char for char in text if not char.isspace()]
    if not chars:
        return 0.0
    bad = sum(char == REPLACEMENT_CHAR or is_private_use(char) for char in chars)
    return bad / len(chars)


def text_layer_is_broken(text: str, source: str = AUTO) -> bool:
    """Decide whether a page's embedded text layer is unusable for translation.

    A layer is broken when too many characters are unreadable, or when the
    declared source language is known and its script barely appears in the
    text: the classic signature of a legacy (non-Unicode) Indic font.
    """
    if unreadable_share(text) > MAX_UNREADABLE_SHARE:
        return True
    if source == AUTO:
        return False
    letters = sum(char.isalpha() or is_private_use(char) for char in text)
    if letters < MIN_LETTERS:
        return False
    return script_share(text, get_language(source).script) < MIN_SCRIPT_SHARE
