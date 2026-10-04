"""Translation backends.

Every backend implements one method, ``translate(texts, source, target)``, that
maps a batch of paragraphs to their translations. Two backends ship with the
project:

* ``google``: Google Translate over plain HTTPS. No API key, every language in
  the registry, automatic source-language detection.
* ``indictrans``: AI4Bharat's IndicTrans2, a model trained specifically on the
  22 scheduled Indian languages. Runs fully offline on your own CPU/GPU once
  the weights are downloaded. Install with ``pip install "pdf-linguist[indictrans]"``.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from typing import ClassVar, Protocol

import requests

from .languages import AUTO, get_language


class TranslationError(RuntimeError):
    """Raised when a backend cannot translate a piece of text."""


class RateLimitedError(TranslationError):
    """Raised when the service keeps refusing requests; retrying other blocks is pointless."""


class Translator(Protocol):
    name: str

    def translate(self, texts: Sequence[str], source: str, target: str) -> list[str]: ...


_SENTENCE_END = re.compile(r"(?<=[.!?।॥。！？])\s+")


def split_sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation, including the Indic danda (। ॥)."""
    return [part for part in _SENTENCE_END.split(text.strip()) if part]


def chunk_text(text: str, limit: int) -> list[str]:
    """Split ``text`` into pieces of at most ``limit`` characters on sentence boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        while len(sentence) > limit:  # a single run-on "sentence": hard split on a space
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if current and len(current) + 1 + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current)
    return chunks


class GoogleTranslator:
    """Google Translate via its public web endpoint (no API key required)."""

    name = "google"
    URL = "https://translate.googleapis.com/translate_a/single"
    MAX_CHARS = 4500

    def __init__(self, timeout: float = 20.0, retries: int = 3, session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()

    @staticmethod
    def parse(payload: list) -> str:
        """Extract the translated text from the endpoint's nested-list response ("" if unrecognised)."""
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
            return ""
        segments = [segment for segment in payload[0] if isinstance(segment, list) and segment]
        return "".join(segment[0] for segment in segments if isinstance(segment[0], str))

    def _request(self, text: str, source: str, target: str) -> str:
        params = {"client": "gtx", "sl": source, "tl": target, "dt": "t"}
        delay = 1.0
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(self.URL, params=params, data={"q": text}, timeout=self.timeout)
                if response.status_code == 200:
                    return self.parse(response.json())
                retryable = response.status_code == 429 or response.status_code >= 500
                error = f"HTTP {response.status_code}"
            except (requests.RequestException, ValueError) as exc:
                retryable, error = True, str(exc)
            if not retryable or attempt == self.retries:
                if error == "HTTP 429":
                    raise RateLimitedError(
                        "Google Translate is rate-limiting this network (HTTP 429). "
                        "Wait a few minutes and retry, or use the offline IndicTrans2 engine."
                    )
                raise TranslationError(f"Google Translate failed: {error}")
            time.sleep(delay)
            delay *= 2
        raise AssertionError("unreachable")

    def translate(self, texts: Sequence[str], source: str, target: str) -> list[str]:
        source = AUTO if source == AUTO else get_language(source).code
        target = get_language(target).code
        return [
            " ".join(self._request(chunk, source, target) for chunk in chunk_text(text, self.MAX_CHARS))
            for text in texts
        ]


class IndicTransTranslator:
    """AI4Bharat IndicTrans2 (1B) running locally through Hugging Face Transformers.

    Supports English ↔ Indian languages and Indian ↔ Indian languages. The
    source language must be chosen explicitly: IndicTrans2 does not auto-detect.
    """

    name = "indictrans"
    requires_source = True
    MODELS: ClassVar[dict[str, str]] = {
        "en-indic": "ai4bharat/indictrans2-en-indic-1B",
        "indic-en": "ai4bharat/indictrans2-indic-en-1B",
        "indic-indic": "ai4bharat/indictrans2-indic-indic-1B",
    }

    def __init__(self, device: str | None = None, batch_size: int = 8, max_length: int = 256) -> None:
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            try:
                from IndicTransToolkit.processor import IndicProcessor
            except ImportError:  # IndicTransToolkit < 1.0
                from IndicTransToolkit import IndicProcessor
        except ImportError as exc:
            raise TranslationError('IndicTrans2 needs extra packages: pip install "pdf-linguist[indictrans]"') from exc

        self._torch = torch
        self._model_cls = AutoModelForSeq2SeqLM
        self._tokenizer_cls = AutoTokenizer
        self.processor = IndicProcessor(inference=True)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self.max_length = max_length
        self._loaded: dict[str, tuple] = {}

    def _model(self, direction: str):
        if direction not in self._loaded:
            checkpoint = self.MODELS[direction]
            tokenizer = self._tokenizer_cls.from_pretrained(checkpoint, trust_remote_code=True)
            model = self._model_cls.from_pretrained(checkpoint, trust_remote_code=True).to(self.device).eval()
            self._loaded[direction] = (tokenizer, model)
        return self._loaded[direction]

    def _generate(self, sentences: list[str], src: str, tgt: str, direction: str) -> list[str]:
        tokenizer, model = self._model(direction)
        results: list[str] = []
        for start in range(0, len(sentences), self.batch_size):
            chunk = sentences[start : start + self.batch_size]
            batch = self.processor.preprocess_batch(chunk, src_lang=src, tgt_lang=tgt)
            inputs = tokenizer(
                batch, truncation=True, padding="longest", return_tensors="pt", return_attention_mask=True
            ).to(self.device)
            with self._torch.no_grad():
                tokens = model.generate(
                    **inputs,
                    use_cache=True,
                    min_length=0,
                    max_length=self.max_length,
                    num_beams=5,
                    num_return_sequences=1,
                )
            decoded = tokenizer.batch_decode(tokens, skip_special_tokens=True, clean_up_tokenization_spaces=True)
            results.extend(self.processor.postprocess_batch(decoded, lang=tgt))
        return results

    def translate(self, texts: Sequence[str], source: str, target: str) -> list[str]:
        if source == AUTO:
            raise TranslationError("IndicTrans2 cannot auto-detect the source language; choose it explicitly.")
        src_lang, tgt_lang = get_language(source), get_language(target)
        if not (src_lang.flores and tgt_lang.flores):
            raise TranslationError(
                f"IndicTrans2 only covers English and Indian languages, not {src_lang.name} → {tgt_lang.name}."
            )
        if src_lang.code == "en" and tgt_lang.code == "en":
            return list(texts)
        direction = "indic-en" if tgt_lang.code == "en" else ("en-indic" if src_lang.code == "en" else "indic-indic")

        # Translate sentence by sentence (the model's context is 256 tokens), then re-assemble paragraphs.
        sentences: list[str] = []
        spans: list[tuple[int, int]] = []
        for text in texts:
            parts = split_sentences(text) or [text]
            spans.append((len(sentences), len(sentences) + len(parts)))
            sentences.extend(parts)
        translated = self._generate(sentences, src_lang.flores, tgt_lang.flores, direction)
        return [" ".join(translated[start:end]) for start, end in spans]


class CachedTranslator:
    """Wraps a backend so repeated paragraphs (headers, footers, labels) are translated once."""

    def __init__(self, backend: Translator) -> None:
        self.backend = backend
        self.name = backend.name
        self.requires_source = getattr(backend, "requires_source", False)
        self._cache: dict[tuple[str, str, str], str] = {}

    def translate(self, texts: Sequence[str], source: str, target: str) -> list[str]:
        missing = list(dict.fromkeys(text for text in texts if (text, source, target) not in self._cache))
        if missing:
            for text, result in zip(missing, self.backend.translate(missing, source, target), strict=True):
                self._cache[(text, source, target)] = result
        return [self._cache[(text, source, target)] for text in texts]


BACKENDS = {GoogleTranslator.name: GoogleTranslator, IndicTransTranslator.name: IndicTransTranslator}


def get_translator(name: str = GoogleTranslator.name) -> CachedTranslator:
    """Build a cached translator for the backend called ``name``."""
    try:
        backend = BACKENDS[name]
    except KeyError:
        raise ValueError(f"Unknown translator {name!r}. Choose from: {', '.join(BACKENDS)}") from None
    return CachedTranslator(backend())
