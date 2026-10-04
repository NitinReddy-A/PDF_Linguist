import argparse

import pytest

from pdf_linguist import cli
from pdf_linguist.pipeline import TranslationReport

from .conftest import make_pdf


def test_parse_pages():
    assert cli.parse_pages("1-3,5") == [1, 2, 3, 5]
    assert cli.parse_pages(" 4 , 2-2 ") == [2, 4]


@pytest.mark.parametrize("spec", ["", "0", "3-1", "a", "1-b"])
def test_parse_pages_rejects_bad_input(spec):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_pages(spec)


def test_main_writes_output(tmp_path, monkeypatch, capsys):
    source = tmp_path / "notice.pdf"
    source.write_bytes(make_pdf())
    seen = {}

    def fake_translate(path, options, progress=None):
        seen["options"] = options
        return b"%PDF-translated", TranslationReport()

    monkeypatch.setattr(cli, "translate_pdf", fake_translate)
    assert cli.main([str(source), "--to", "kn", "--from", "en", "-p", "1"]) == 0

    assert (tmp_path / "notice.kn.pdf").read_bytes() == b"%PDF-translated"
    assert seen["options"].source == "en" and seen["options"].pages == [1]
    assert "notice.kn.pdf" in capsys.readouterr().out


def test_main_reports_missing_file(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.pdf"), "--to", "kn"]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_main_reports_bad_language(tmp_path, capsys):
    source = tmp_path / "notice.pdf"
    source.write_bytes(make_pdf())
    assert cli.main([str(source), "--to", "klingon"]) == 1
    assert "Unsupported language" in capsys.readouterr().err
