"""Unit tests for the markdown_to_pdf tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from atria.core.context_engineering.tools.implementations.md_to_pdf_tool import (
    MarkdownToPdfHandler,
    WEASYPRINT_AVAILABLE,
)

needs_weasyprint = pytest.mark.skipif(
    not WEASYPRINT_AVAILABLE,
    reason="WeasyPrint native deps (pango) not installed on this host",
)


@pytest.fixture
def handler() -> MarkdownToPdfHandler:
    return MarkdownToPdfHandler()


def _call(handler: MarkdownToPdfHandler, **kwargs) -> dict:
    return handler.convert(kwargs, context=None)


@needs_weasyprint
def test_simple_md(tmp_path: Path, handler: MarkdownToPdfHandler) -> None:
    md = tmp_path / "in.md"
    md.write_text("# Hello\n\nSome **bold** text.\n", encoding="utf-8")
    pdf = tmp_path / "out.pdf"

    res = _call(handler, md_path=str(md), pdf_path=str(pdf))
    assert res["success"] is True, res
    assert pdf.exists()
    assert pdf.stat().st_size > 0
    assert res["output"]["bytes"] == pdf.stat().st_size


@needs_weasyprint
def test_embedded_image(tmp_path: Path, handler: MarkdownToPdfHandler) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(2, 2))
    ax.plot([0, 1], [0, 1])
    img = tmp_path / "chart.png"
    fig.savefig(img)
    plt.close(fig)

    md = tmp_path / "report.md"
    md.write_text("# Report\n\n![chart](./chart.png)\n", encoding="utf-8")
    pdf = tmp_path / "report.pdf"

    res = _call(handler, md_path=str(md), pdf_path=str(pdf))
    assert res["success"] is True, res
    assert pdf.exists()
    assert pdf.stat().st_size > 5_000


def test_missing_md(tmp_path: Path, handler: MarkdownToPdfHandler) -> None:
    res = _call(handler, md_path=str(tmp_path / "nope.md"), pdf_path=str(tmp_path / "x.pdf"))
    assert res["success"] is False
    assert "not found" in res["error"].lower()


def test_wrong_pdf_extension(tmp_path: Path, handler: MarkdownToPdfHandler) -> None:
    md = tmp_path / "in.md"
    md.write_text("# x", encoding="utf-8")
    res = _call(handler, md_path=str(md), pdf_path=str(tmp_path / "out.txt"))
    assert res["success"] is False
    assert ".pdf" in res["error"]
