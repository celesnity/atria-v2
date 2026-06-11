"""Unit tests for the render_chart tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from atria.core.context_engineering.tools.implementations.chart_tool import (
    RenderChartHandler,
)

FIXTURE = Path(__file__).parent / "fixtures" / "analyze_sample.csv"


@pytest.fixture
def handler() -> RenderChartHandler:
    return RenderChartHandler()


def _call(handler: RenderChartHandler, **kwargs) -> dict:
    return handler.render(kwargs, context=None)


def test_bar_chart(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "bar.png"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="bar",
        x="region",
        y=["sales"],
        title="Sales by region",
        out_path=str(out),
        agg="sum",
    )
    assert res["success"] is True, res
    assert out.exists()
    assert res["output"]["path"] == str(out)
    assert res["output"]["rows_plotted"] == 4  # 4 distinct regions


def test_line_chart_by_date(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "line.png"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="line",
        x="month",
        y=["sales"],
        title="Sales over time",
        out_path=str(out),
        agg="sum",
    )
    assert res["success"] is True, res
    assert out.exists()


def test_scatter(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "scatter.png"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="scatter",
        x="units",
        y=["sales"],
        title="Sales vs units",
        out_path=str(out),
    )
    assert res["success"] is True, res
    assert out.exists()


def test_hist(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "hist.png"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="hist",
        x="",
        y=["sales"],
        title="Sales distribution",
        out_path=str(out),
    )
    assert res["success"] is True, res
    assert out.exists()


def test_missing_column(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "x.png"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="bar",
        x="region",
        y=["nope"],
        title="x",
        out_path=str(out),
    )
    assert res["success"] is False
    assert "nope" in res["error"]
    assert not out.exists()


def test_non_numeric_y(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "x.png"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="bar",
        x="region",
        y=["month"],
        title="x",
        out_path=str(out),
    )
    assert res["success"] is False
    assert "numeric" in res["error"].lower()


def test_wrong_extension(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "bar.jpg"
    res = _call(
        handler,
        data_path=str(FIXTURE),
        chart_type="bar",
        x="region",
        y=["sales"],
        title="x",
        out_path=str(out),
    )
    assert res["success"] is False
    assert ".png" in res["error"]


def test_missing_file(tmp_path: Path, handler: RenderChartHandler) -> None:
    out = tmp_path / "bar.png"
    res = _call(
        handler,
        data_path=str(tmp_path / "nope.csv"),
        chart_type="bar",
        x="region",
        y=["sales"],
        title="x",
        out_path=str(out),
    )
    assert res["success"] is False
    assert "not found" in res["error"].lower() or "no such" in res["error"].lower()
