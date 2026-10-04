import pytest
import requests

from pdf_linguist.translation import (
    CachedTranslator,
    GoogleTranslator,
    IndicTransTranslator,
    RateLimitedError,
    TranslationError,
    chunk_text,
    get_translator,
    split_sentences,
)


def test_split_sentences_handles_danda():
    text = "यह पहला वाक्य है। यह दूसरा है॥ And English? Yes."
    assert split_sentences(text) == ["यह पहला वाक्य है।", "यह दूसरा है॥", "And English?", "Yes."]


def test_chunk_text_respects_limit_and_keeps_content():
    text = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_text(text, 300)
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert " ".join(chunks) == text


def test_chunk_text_splits_run_on_sentences():
    text = "word " * 200
    chunks = chunk_text(text.strip(), 100)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert " ".join(chunks).split() == text.split()


def test_google_parse_joins_segments():
    payload = [[["ನಮಸ್ಕಾರ. ", "Hello. ", None], ["ಹೇಗಿದ್ದೀರಿ?", "How are you?", None]], None, "en"]
    assert GoogleTranslator.parse(payload) == "ನಮಸ್ಕಾರ. ಹೇಗಿದ್ದೀರಿ?"
    assert GoogleTranslator.parse([None]) == ""
    assert GoogleTranslator.parse({"error": "unexpected"}) == ""


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, params, data, timeout):
        self.requests.append((params, data))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("pdf_linguist.translation.time.sleep", lambda seconds: None)


def test_google_retries_transient_errors():
    ok = FakeResponse(200, [[["ಹಲೋ", "Hello", None]]])
    session = FakeSession([requests.ConnectionError("reset"), FakeResponse(503), ok])
    translator = GoogleTranslator(session=session)
    assert translator.translate(["Hello"], "auto", "kn") == ["ಹಲೋ"]
    params, data = session.requests[-1]
    assert params["sl"] == "auto" and params["tl"] == "kn" and data == {"q": "Hello"}


def test_google_rate_limit_is_fatal():
    session = FakeSession([FakeResponse(429)] * 4)
    with pytest.raises(RateLimitedError, match="rate-limiting"):
        GoogleTranslator(session=session, retries=3).translate(["Hello"], "en", "hi")


def test_google_client_errors_are_not_retried():
    session = FakeSession([FakeResponse(400)])
    with pytest.raises(TranslationError, match="HTTP 400"):
        GoogleTranslator(session=session).translate(["Hello"], "en", "hi")
    assert len(session.requests) == 1


def test_google_rejects_unknown_target():
    with pytest.raises(ValueError):
        GoogleTranslator(session=FakeSession([])).translate(["Hello"], "en", "xx")


def test_cache_translates_each_paragraph_once():
    class Counting:
        name = "counting"

        def __init__(self):
            self.seen: list[str] = []

        def translate(self, texts, source, target):
            self.seen.extend(texts)
            return [text.upper() for text in texts]

    backend = Counting()
    cached = CachedTranslator(backend)
    assert cached.translate(["a", "b", "a"], "en", "fr") == ["A", "B", "A"]
    assert cached.translate(["b", "c"], "en", "fr") == ["B", "C"]
    assert backend.seen == ["a", "b", "c"]


def test_get_translator():
    assert get_translator("google").name == "google"
    with pytest.raises(ValueError, match="Unknown translator"):
        get_translator("babelfish")


def test_indictrans_validates_languages_before_loading_models():
    translator = IndicTransTranslator.__new__(IndicTransTranslator)  # skip heavy model imports
    with pytest.raises(TranslationError, match="auto-detect"):
        translator.translate(["x"], "auto", "kn")
    with pytest.raises(TranslationError, match="only covers"):
        translator.translate(["x"], "en", "fr")
