import pytest
from minder.core.knowledge.parsing import SUPPORTED_EXTENSIONS, parse_file


def test_reads_markdown(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\nBody text", encoding="utf-8")
    assert "Body text" in parse_file(str(p))


def test_reads_plain_text(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")
    assert parse_file(str(p)) == "hello world"


def test_unknown_extension_rejected(tmp_path):
    p = tmp_path / "a.docx"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_file(str(p))


def test_supported_extensions_set():
    assert ".pdf" in SUPPORTED_EXTENSIONS and ".md" in SUPPORTED_EXTENSIONS
