"""Language and script registry.

Every language PDF Linguist understands is described once here: its translation
code, the Tesseract model used to OCR it, its IndicTrans2 (FLORES-200) code and
the Unicode script it is written in. The rest of the engine looks languages up
in this table instead of hard-coding codes.
"""

from __future__ import annotations

from dataclasses import dataclass

AUTO = "auto"


@dataclass(frozen=True)
class Script:
    """A writing system and the Unicode ranges its letters live in."""

    name: str
    ranges: tuple[tuple[int, int], ...]
    rtl: bool = False

    def contains(self, char: str) -> bool:
        point = ord(char)
        return any(start <= point <= end for start, end in self.ranges)


SCRIPTS: dict[str, Script] = {
    script.name: script
    for script in (
        Script("Latin", ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))),
        Script("Devanagari", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
        Script("Bengali", ((0x0980, 0x09FF),)),
        Script("Gurmukhi", ((0x0A00, 0x0A7F),)),
        Script("Gujarati", ((0x0A80, 0x0AFF),)),
        Script("Oriya", ((0x0B00, 0x0B7F),)),
        Script("Tamil", ((0x0B80, 0x0BFF),)),
        Script("Telugu", ((0x0C00, 0x0C7F),)),
        Script("Kannada", ((0x0C80, 0x0CFF),)),
        Script("Malayalam", ((0x0D00, 0x0D7F),)),
        Script("Arabic", ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)), rtl=True),
        Script("Cyrillic", ((0x0400, 0x04FF),)),
        Script("Han", ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))),
        Script("Japanese", ((0x3040, 0x30FF), (0x4E00, 0x9FFF))),
    )
}


@dataclass(frozen=True)
class Language:
    """A language PDF Linguist can read (OCR) and/or write (translate into)."""

    code: str  # Google Translate / ISO 639-1 style code
    name: str
    native_name: str
    script: str  # key into SCRIPTS
    tesseract: str  # Tesseract traineddata name
    flores: str | None = None  # IndicTrans2 / FLORES-200 code, None if unsupported
    indic: bool = False

    @property
    def rtl(self) -> bool:
        return SCRIPTS[self.script].rtl

    @property
    def label(self) -> str:
        if self.native_name == self.name:
            return self.name
        return f"{self.name} · {self.native_name}"


LANGUAGES: tuple[Language, ...] = (
    # Indian languages: the ones the engine is tuned for.
    Language("hi", "Hindi", "हिन्दी", "Devanagari", "hin", "hin_Deva", indic=True),
    Language("kn", "Kannada", "ಕನ್ನಡ", "Kannada", "kan", "kan_Knda", indic=True),
    Language("ta", "Tamil", "தமிழ்", "Tamil", "tam", "tam_Taml", indic=True),
    Language("te", "Telugu", "తెలుగు", "Telugu", "tel", "tel_Telu", indic=True),
    Language("ml", "Malayalam", "മലയാളം", "Malayalam", "mal", "mal_Mlym", indic=True),
    Language("bn", "Bengali", "বাংলা", "Bengali", "ben", "ben_Beng", indic=True),
    Language("mr", "Marathi", "मराठी", "Devanagari", "mar", "mar_Deva", indic=True),
    Language("gu", "Gujarati", "ગુજરાતી", "Gujarati", "guj", "guj_Gujr", indic=True),
    Language("pa", "Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi", "pan", "pan_Guru", indic=True),
    Language("or", "Odia", "ଓଡ଼ିଆ", "Oriya", "ori", "ory_Orya", indic=True),
    Language("as", "Assamese", "অসমীয়া", "Bengali", "asm", "asm_Beng", indic=True),
    Language("ne", "Nepali", "नेपाली", "Devanagari", "nep", "npi_Deva", indic=True),
    Language("sa", "Sanskrit", "संस्कृतम्", "Devanagari", "san", "san_Deva", indic=True),
    Language("ur", "Urdu", "اردو", "Arabic", "urd", "urd_Arab", indic=True),
    # English bridges Indian and foreign languages.
    Language("en", "English", "English", "Latin", "eng", "eng_Latn"),
    # Foreign languages.
    Language("fr", "French", "Français", "Latin", "fra"),
    Language("de", "German", "Deutsch", "Latin", "deu"),
    Language("es", "Spanish", "Español", "Latin", "spa"),
    Language("pt", "Portuguese", "Português", "Latin", "por"),
    Language("it", "Italian", "Italiano", "Latin", "ita"),
    Language("ru", "Russian", "Русский", "Cyrillic", "rus"),
    Language("ar", "Arabic", "العربية", "Arabic", "ara"),
    Language("zh-CN", "Chinese (Simplified)", "简体中文", "Han", "chi_sim"),
    Language("ja", "Japanese", "日本語", "Japanese", "jpn"),
)

_BY_CODE = {language.code.lower(): language for language in LANGUAGES}


def get_language(code: str) -> Language:
    """Return the language registered under ``code`` (case-insensitive)."""
    try:
        return _BY_CODE[code.lower()]
    except KeyError:
        supported = ", ".join(language.code for language in LANGUAGES)
        raise ValueError(f"Unsupported language {code!r}. Supported: {supported}") from None


def ocr_languages(source: str) -> str:
    """Tesseract language string for a source language (``auto`` reads English).

    English is always included so that numbers, codes and English fragments that
    appear inside Indian-language documents are recognised too.
    """
    if source == AUTO:
        return "eng"
    model = get_language(source).tesseract
    return model if model == "eng" else f"{model}+eng"
