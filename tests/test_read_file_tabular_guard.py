"""read_file must degrade large tabular files to a bounded read, not refuse.

Regression: an 18MB CSV was hard-rejected even when the caller passed
``max_lines``, leaving the agent unable to inspect the file at all. The guard
now samples/truncates instead of failing, and a char backstop bounds wide rows.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from atria.core.context_engineering.tools.handlers.file_handlers import FileToolHandler


class RecordingFileOps:
    """Minimal file_ops stand-in that records how read_file was called."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.next_output = "  1\theader\n  2\trow"
        self.working_dir = None  # consulted by _get_file_instruction

    def read_file(self, file_path, offset=None, max_lines=None):
        self.calls.append({"offset": offset, "max_lines": max_lines})
        return self.next_output


@pytest.fixture
def big_csv():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data_processed.csv"
        # > 1 MB so the tabular guard engages.
        path.write_text("\n".join("a,b,c,d,e" for _ in range(200_000)))
        assert path.stat().st_size > 1_000_000
        yield str(path)


def _handler(file_ops):
    return FileToolHandler(file_ops, write_tool=None, edit_tool=None)


def test_large_csv_without_bounds_is_sampled_not_rejected(big_csv):
    ops = RecordingFileOps()
    handler = _handler(ops)

    result = handler.read_file({"file_path": big_csv})

    assert result["success"] is True
    # Auto-degraded to a bounded sample instead of failing.
    assert ops.calls[0]["max_lines"] == FileToolHandler.TABULAR_SAMPLE_LINES
    assert "auto-sampled" in result["output"]


def test_explicit_max_lines_is_respected(big_csv):
    ops = RecordingFileOps()
    handler = _handler(ops)

    result = handler.read_file({"file_path": big_csv, "max_lines": 50})

    assert result["success"] is True
    # Caller's bound wins; we do not override it with the sample default.
    assert ops.calls[0]["max_lines"] == 50


def test_wide_output_is_clamped_by_char_budget(big_csv):
    ops = RecordingFileOps()
    # Simulate a few extremely wide rows exceeding the char budget.
    ops.next_output = "  1\t" + ("x" * (FileToolHandler.MAX_READ_OUTPUT_CHARS + 5000))
    handler = _handler(ops)

    result = handler.read_file({"file_path": big_csv, "max_lines": 5})

    assert result["success"] is True
    assert len(result["output"]) <= FileToolHandler.MAX_READ_OUTPUT_CHARS + 256
    assert "output truncated" in result["output"]


def test_small_csv_is_untouched(tmp_path):
    csv = tmp_path / "small.csv"
    csv.write_text("a,b,c\n1,2,3\n")
    ops = RecordingFileOps()
    handler = _handler(ops)

    result = handler.read_file({"file_path": str(csv)})

    assert result["success"] is True
    # No auto-sampling for a small file.
    assert ops.calls[0]["max_lines"] is None
    assert "auto-sampled" not in result["output"]
