"""On-disk file storage for uploaded/seeded documents.

Files live under ``<module>/data/uploads/<dept_code>/`` (overridable via
``AIW_UPLOADS_DIR``). The DB stores a path *relative to the uploads root*, so the
same relative path resolves under whatever root the environment points at — which
keeps tests hermetic and the store portable.
"""
from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path


def uploads_root() -> Path:
    """Return ``AIW_UPLOADS_DIR`` if set, else ``<module>/data/uploads``."""
    override = os.environ.get("AIW_UPLOADS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "uploads"


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """Reduce a filename to a safe basename (no path parts, restricted charset)."""
    base = Path(str(name)).name or "file"
    cleaned = _UNSAFE.sub("_", base).strip("._-")
    return cleaned or "file"


def guess_mime(filename: str) -> str:
    """Best-effort MIME type; markdown/text fall back sensibly."""
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        return mime
    if filename.lower().endswith(".md"):
        return "text/markdown"
    return "application/octet-stream"


def save_upload(
    src_file: str, dept_code: str, doc_id: str, filename: str | None = None
) -> tuple[str, int, str]:
    """Copy ``src_file`` into ``uploads/<dept>/<doc_id>_<safe>``.

    Returns ``(relative_path, size_bytes, mime_type)`` where ``relative_path`` is
    relative to :func:`uploads_root`.
    """
    src = Path(src_file)
    fname = safe_filename(filename or src.name)
    dest_dir = uploads_root() / dept_code
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{doc_id}_{fname}"
    data = src.read_bytes()
    dest.write_bytes(data)
    rel = dest.relative_to(uploads_root())
    return str(rel).replace("\\", "/"), len(data), guess_mime(fname)


def abs_path(relative_path: str) -> str:
    """Resolve a stored relative path to an absolute path on disk."""
    return str(uploads_root() / relative_path)


def exists(relative_path: str) -> bool:
    """Whether a stored file exists under the uploads root."""
    return (uploads_root() / relative_path).is_file()


def sidecar_path(relative_path: str) -> str:
    """The companion extracted-text path for a stored file (``<file>.txt``)."""
    return relative_path + ".txt"


def pdf_cache_path(relative_path: str) -> str:
    """The companion converted-PDF path for an office file (``<file>.pdf``)."""
    return relative_path + ".pdf"


def write_pdf_cache(relative_path: str, data: bytes) -> str:
    """Cache a converted PDF next to the source file; return its relative path."""
    rel = pdf_cache_path(relative_path)
    dest = uploads_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return rel


def write_sidecar(relative_path: str, text: str) -> str:
    """Write extracted text next to a stored file; return its relative path."""
    rel = sidecar_path(relative_path)
    dest = uploads_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return rel


def read_bytes(relative_path: str) -> bytes:
    """Read the stored file at ``relative_path`` (relative to the uploads root)."""
    return (uploads_root() / relative_path).read_bytes()


def read_text(relative_path: str) -> str:
    """Read a stored text file as UTF-8."""
    return (uploads_root() / relative_path).read_text(encoding="utf-8")


def is_text(mime_type: str, filename: str) -> bool:
    """Whether the file can be returned inline as text."""
    if mime_type.startswith("text/") or mime_type == "application/json":
        return True
    return filename.lower().endswith((".md", ".txt", ".csv", ".json"))
