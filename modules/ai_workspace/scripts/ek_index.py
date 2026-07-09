"""Adapter to EK's ingest_api.

Lazy import + fail-soft: indexing must never break an upload. On any failure the
caller marks the document ``index_status='failed'`` and can retry via ``reindex``.
The EK entry (``ingest_api``) is deliberately audit-free, so importing it in this
process does not collide with ai_workspace's own ``audit`` module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EK_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "enterprise_knowledge" / "scripts"


def _api():
    """Import EK's slim ingest_api with EK's scripts dir on sys.path."""
    if str(_EK_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_EK_SCRIPTS))
    import ingest_api  # type: ignore[import-not-found]

    return ingest_api


def index_document(
    doc_id: str, title: str, dept_code: str, classification: str, text: str, owner: str
) -> bool:
    """Ingest one document into EK. Returns True on success, False on any failure."""
    try:
        _api().ingest_document(
            doc_id=doc_id, title=title, department=dept_code,
            classification=classification, text=text, owner=owner,
        )
        return True
    except Exception:  # noqa: BLE001 - never break the upload
        return False


def remove_document(doc_id: str) -> bool:
    """Remove a document's chunks from EK. Returns True on success, else False."""
    try:
        _api().remove_document(doc_id=doc_id)
        return True
    except Exception:  # noqa: BLE001
        return False


def reindex(docs: list[dict]) -> bool:
    """Rebuild the EK index from active-document dicts. Returns False on failure."""
    try:
        _api().reindex_documents(docs)
        return True
    except Exception:  # noqa: BLE001
        return False
