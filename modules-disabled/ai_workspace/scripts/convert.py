"""Convert office documents to PDF via LibreOffice headless.

Used for faithful, in-format preview of Word/PowerPoint/Excel files: the browser
renders the resulting PDF exactly as laid out. Conversion is on-demand (at read
time) and the result is cached next to the source, so repeat reads are instant.

Requires the ``soffice`` binary (LibreOffice) — baked into the container image.
Returns ``None`` gracefully when the binary is absent so callers fall back to
extracted text.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

OFFICE_EXT = {
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".odt", ".odp", ".ods", ".rtf",
}


def is_office(name: str) -> bool:
    """Whether a filename is a LibreOffice-convertible office document."""
    return Path(str(name)).suffix.lower() in OFFICE_EXT


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def to_pdf(src_path: str, timeout: int = 90) -> bytes | None:
    """Convert ``src_path`` to PDF and return its bytes, or ``None`` on failure.

    Uses an isolated LibreOffice user profile per call so concurrent conversions
    don't collide on the shared profile lock.
    """
    exe = _soffice()
    if not exe:
        return None
    src = Path(src_path)
    if not src.is_file():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        cmd = [
            exe, "--headless", "--norestore",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to", "pdf", "--outdir", tmp, str(src),
        ]
        try:
            subprocess.run(
                cmd, timeout=timeout, capture_output=True,
                env=dict(os.environ), check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return None
        out = Path(tmp) / (src.stem + ".pdf")
        if out.is_file():
            return out.read_bytes()
    return None
