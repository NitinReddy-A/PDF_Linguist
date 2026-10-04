import pytest

from pdf_linguist.languages import AUTO, LANGUAGES, SCRIPTS, get_language, ocr_languages


def test_codes_are_unique():
    codes = [language.code.lower() for language in LANGUAGES]
    assert len(codes) == len(set(codes))


def test_every_language_has_a_known_script():
    assert all(language.script in SCRIPTS for language in LANGUAGES)


def test_lookup_is_case_insensitive():
    assert get_language("KN").name == "Kannada"
    assert get_language("zh-cn").code == "zh-CN"


def test_unknown_language_lists_supported_codes():
    with pytest.raises(ValueError, match="Supported"):
        get_language("xx")


def test_indic_languages_have_indictrans_codes():
    assert all(language.flores for language in LANGUAGES if language.indic)


def test_rtl_follows_script():
    assert get_language("ur").rtl and get_language("ar").rtl
    assert not get_language("kn").rtl


@pytest.mark.parametrize(
    ("source", "expected"),
    [(AUTO, "eng"), ("en", "eng"), ("kn", "kan+eng"), ("hi", "hin+eng"), ("or", "ori+eng")],
)
def test_ocr_languages(source, expected):
    assert ocr_languages(source) == expected


def test_script_contains():
    kannada = SCRIPTS["Kannada"]
    assert kannada.contains("ಕ")
    assert not kannada.contains("क")
