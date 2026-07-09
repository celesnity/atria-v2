"""Office→PDF conversion helper (graceful without a LibreOffice binary)."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import convert  # noqa: E402


def test_is_office():
    assert convert.is_office("report.docx")
    assert convert.is_office("deck.PPTX")
    assert convert.is_office("sheet.xlsx")
    assert not convert.is_office("scan.pdf")
    assert not convert.is_office("photo.png")
    assert not convert.is_office("note.md")


def test_to_pdf_missing_file_is_none(tmp_path):
    assert convert.to_pdf(str(tmp_path / "does_not_exist.docx")) is None


def test_to_pdf_returns_bytes_or_none(tmp_path):
    # A real .docx: converts to PDF bytes where LibreOffice exists, else None —
    # never raises. (In the container this yields a PDF; on a bare host, None.)
    import pytest

    docxmod = pytest.importorskip("docx")
    path = tmp_path / "d.docx"
    doc = docxmod.Document()
    doc.add_paragraph("Xin chào")
    doc.save(str(path))
    result = convert.to_pdf(str(path))
    assert result is None or (isinstance(result, bytes) and result[:4] == b"%PDF")
