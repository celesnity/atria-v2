import pytest

from minder.core.knowledge.cli_ops import format_documents, format_hits


def test_format_documents_table():
    out = format_documents([{"id": 1, "status": "ready", "category": "reference_docs", "title": "Doc"}])
    assert "ready" in out and "Doc" in out and "1" in out


def test_format_hits_lists_citations():
    hits = [{"metadata": {"citation": "A [1] · 1#0"}, "snippet": "alpha"}]
    out = format_hits(hits)
    assert "A [1] · 1#0" in out and "alpha" in out
