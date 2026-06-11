"""Input validation for deep_analyze."""

from pathlib import Path

import pytest

from atria.skills.builtin.deep_analyze.validation import (
    AnalyzeValidationError,
    validate_input,
)


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AnalyzeValidationError, match="not found"):
        validate_input(str(tmp_path / "nope.csv"))


def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    p = _write(tmp_path, "data.json", b"{}")
    with pytest.raises(AnalyzeValidationError, match="extension"):
        validate_input(str(p))


def test_rejects_oversize_file(tmp_path: Path) -> None:
    p = _write(tmp_path, "big.csv", b"a,b\n" + b"1,2\n" * 3_000_000)  # > 10 MB
    with pytest.raises(AnalyzeValidationError, match="size"):
        validate_input(str(p))


def test_accepts_small_csv(tmp_path: Path) -> None:
    p = _write(tmp_path, "ok.csv", b"a,b\n1,2\n3,4\n")
    validate_input(str(p))  # no raise
