import unicodedata

from pdf_linguist.encoding import has_letters, normalize, script_share, text_layer_is_broken, unreadable_share

KANNADA = "ರಶೀದಾ ಪತ್ರಿಕೆ ಓದುತ್ತಾ ಕುಳಿತಿದ್ದಳು. ಇದ್ದಕ್ಕಿದ್ದಂತೆ ಅವಳ ಕಣ್ಣುಗಳು ಒಂದು ಸಣ್ಣ ಶೀರ್ಷಿಕೆಯ ಮೇಲೆ ಬಿದ್ದವು."
# What a Nudi/Baraha (legacy, non-Unicode) Kannada text layer typically extracts as.
LEGACY_KANNADA = "gÀ²Ã¢Á ¥ÀwæPÉ NzÀÄvÁÛ PÀÄ½wzÀݼÀÄ. EzÀÝQÌzÀÝAvÉ CªÀ¼À PÀtÄÚUÀ¼ÀÄ MAzÀÄ"


def test_normalize_composes_and_collapses_whitespace():
    decomposed = unicodedata.normalize("NFD", "क़िला")  # nukta form decomposes
    assert normalize(f"  {decomposed}\n\tपर  ") == unicodedata.normalize("NFC", "क़िला पर")


def test_normalize_keeps_zero_width_joiners():
    text = "ಕ‍ಷ"
    assert normalize(text) == text


def test_has_letters():
    assert has_letters("Page 3")
    assert has_letters("ಕನ್ನಡ")
    assert not has_letters("2018-19 · 42")


def test_script_share():
    assert script_share(KANNADA, "Kannada") > 0.95
    assert script_share(LEGACY_KANNADA, "Kannada") == 0


def test_unicode_kannada_layer_is_trusted():
    assert not text_layer_is_broken(KANNADA, "kn")


def test_legacy_font_layer_is_detected():
    assert text_layer_is_broken(LEGACY_KANNADA, "kn")


def test_auto_source_does_not_guess_script():
    assert not text_layer_is_broken(LEGACY_KANNADA, "auto")


def test_unreadable_characters_break_any_layer():
    garbage = "�� ab "
    assert unreadable_share(garbage) > 0.5
    assert text_layer_is_broken(garbage, "auto")


def test_short_text_is_not_judged():
    assert not text_layer_is_broken("Fig. 3", "kn")


def test_bilingual_page_is_trusted():
    mixed = KANNADA + " Ref: VTU/BGM/Aca-OS/Gen-Cir/2018-19 dated 16 March 2019 Registrar"
    assert not text_layer_is_broken(mixed, "kn")
