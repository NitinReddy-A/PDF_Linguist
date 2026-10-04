# Contributing to PDF Linguist

Thanks for helping make PDF translation work properly for Indian languages. Bug reports with a sample PDF, new languages, better fonts and new translation engines are all welcome.

## Setup

```bash
git clone https://github.com/NitinReddy-A/PDF_Linguist.git
cd PDF_Linguist
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[app,dev]"
```

Before opening a pull request:

```bash
pytest
ruff check . && ruff format --check .
```

The test suite is fully offline. It builds PDFs on the fly and uses a fake translator, so it needs no network, API keys or Tesseract.

## Common contributions

### Add a language

Add one `Language(...)` entry to [`pdf_linguist/languages.py`](pdf_linguist/languages.py) with:

- `code`: the Google Translate code (`kn`, `zh-CN`, ...)
- `script`: a key of `SCRIPTS` (add a `Script` with its Unicode ranges if it is new)
- `tesseract`: the Tesseract model name (`kan`, `hin`, ...)
- `flores`: the IndicTrans2 / FLORES-200 code, if IndicTrans2 supports it, and `indic=True` for Indian languages

### Add or pin a font

Drop a `NotoSans<Script>*.ttf` (or `.otf`) file into [`pdf_linguist/fonts/`](pdf_linguist/fonts), for example `NotoSansTamil-Regular.ttf`, together with its license file. It is picked up automatically for every language written in that script. Without one, MuPDF's built-in Noto fallback is used.

### Add a translation engine

Implement the `Translator` protocol from [`pdf_linguist/translation.py`](pdf_linguist/translation.py):

```python
class MyTranslator:
    name = "mine"

    def translate(self, texts: Sequence[str], source: str, target: str) -> list[str]:
        ...  # one translation per input paragraph, same order
```

Then register it in `BACKENDS`. Raise `TranslationError` for a failed paragraph, and `RateLimitedError` when the service refuses all further requests.

## Reporting bugs

Please include the PDF (or a page that reproduces the problem, with anything private removed), the command or settings you used, and a screenshot of the output. Layout bugs are almost impossible to fix without the source document.

## Ground rules

- Never commit API keys, tokens or `.env` files. The project needs no secrets to run or test.
- Only add sample documents that you have the right to redistribute under the MIT license.
- Keep pull requests focused, and add a test for every behaviour change.
