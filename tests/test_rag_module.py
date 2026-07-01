"""Tests for the local TF-IDF ``rag`` module CLI (modules/rag/scripts/rag.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RAG_PATH = (
    Path(__file__).resolve().parent.parent / "modules" / "rag" / "scripts" / "rag.py"
)


def _load_rag():
    spec = importlib.util.spec_from_file_location("rag_module_under_test", _RAG_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def rag(monkeypatch, tmp_path: Path):
    mod = _load_rag()
    # Redirect the index to a temp dir so tests never touch real module data.
    monkeypatch.setenv("ATRIA_RAG_DIR", str(tmp_path / "idx"))
    return mod


def test_tokenize_drops_stopwords_and_short_tokens(rag):
    assert rag.tokenize("The QUICK brown a fox") == ["quick", "brown", "fox"]


def test_chunk_text_splits_long_input(rag):
    text = "\n\n".join(f"paragraph number {i} " * 40 for i in range(6))
    chunks = rag.chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= rag.CHUNK_SIZE + rag.CHUNK_OVERLAP for c in chunks)


def test_index_then_query_ranks_relevant_file_first(rag, tmp_path, capsys):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "cats.md").write_text(
        "Cats are small felines. Kittens purr and chase mice all day.",
        encoding="utf-8",
    )
    (corpus / "finance.md").write_text(
        "Quarterly revenue growth depends on interest rates and margins.",
        encoding="utf-8",
    )

    assert rag.main(["index", str(corpus)]) == 0
    out = capsys.readouterr().out
    assert "indexed" in out and "2 file(s)" in out

    assert rag.main(["query", "purring kitten chasing mice", "--k", "1"]) == 0
    result = capsys.readouterr().out
    assert "cats.md" in result
    assert "finance.md" not in result


def test_index_accepts_mixed_folder_and_file(rag, tmp_path, capsys):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.txt").write_text("alpha content about apples", encoding="utf-8")
    extra = tmp_path / "extra.md"
    extra.write_text("beta content about bananas", encoding="utf-8")

    assert rag.main(["index", str(folder), str(extra)]) == 0
    out = capsys.readouterr().out
    assert "2 file(s)" in out


def _make_pdf(text: str) -> bytes:
    """Build a minimal, valid single-page PDF with an extractable text layer."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = b"BT /F1 18 Tf 20 100 Td (" + text.encode("latin-1") + b") Tj ET"
    objs.append(
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return out


def test_read_pdf_extracts_text_when_backend_available(rag, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(_make_pdf("kittens purr softly"))
    text = rag._read_pdf(pdf)
    if not text:
        pytest.skip("no PDF backend (poppler/pypdf/PyMuPDF) available")
    assert "kitten" in text.lower()


def test_index_and_query_pdf(rag, tmp_path, capsys):
    pdf = tmp_path / "kittens.pdf"
    pdf.write_bytes(_make_pdf("kittens purr softly and chase mice"))
    if not rag._read_pdf(pdf):
        pytest.skip("no PDF backend available")

    assert rag.main(["index", str(pdf)]) == 0
    capsys.readouterr()
    assert rag.main(["query", "kittens chase mice", "--k", "1"]) == 0
    assert "kittens.pdf" in capsys.readouterr().out


def test_index_skips_unparseable_pdf_but_keeps_text(rag, tmp_path, capsys):
    folder = tmp_path / "mix"
    folder.mkdir()
    (folder / "notes.txt").write_text("alpha bananas apples content", encoding="utf-8")
    (folder / "broken.pdf").write_bytes(b"%PDF-1.4 this is not a real pdf body")

    # A junk PDF must not abort the whole index — the text file still lands.
    assert rag.main(["index", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "1 file(s)" in out


def test_query_without_index_errors(rag):
    assert rag.main(["query", "anything"]) == 1


def test_reset_removes_index(rag, tmp_path, capsys):
    doc = tmp_path / "d.txt"
    doc.write_text("hello world content", encoding="utf-8")
    rag.main(["index", str(doc)])
    capsys.readouterr()
    assert rag.main(["reset"]) == 0
    assert "removed" in capsys.readouterr().out
    assert rag.main(["query", "hello"]) == 1
