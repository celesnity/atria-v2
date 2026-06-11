"""Input validation for deep_analyze."""

from __future__ import annotations

from pathlib import Path

_MAX_FILE_BYTES = 10 * 1024 * 1024
_ALLOWED_EXTS = {".csv", ".xlsx"}


class AnalyzeValidationError(ValueError):
    pass


def validate_input(file_path: str) -> Path:
    p = Path(file_path).expanduser()
    if not p.exists() or not p.is_file():
        raise AnalyzeValidationError(f"File not found: {file_path}")
    if p.suffix.lower() not in _ALLOWED_EXTS:
        raise AnalyzeValidationError(
            f"Unsupported extension {p.suffix!r}; only .csv and .xlsx are accepted."
        )
    size = p.stat().st_size
    if size > _MAX_FILE_BYTES:
        raise AnalyzeValidationError(f"File size {size} bytes exceeds 10 MB limit.")
    return p.resolve()
