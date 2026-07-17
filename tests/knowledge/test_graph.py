import os

from minder.core.knowledge.graph import graph_enabled, merge_graph_hits


def test_merge_prefers_vector_then_graph_and_dedupes():
    merged = merge_graph_hits(["a", "b"], ["b", "c", "d"], cap=3)
    assert merged == ["a", "b", "c"]


def test_merge_truncates_to_cap():
    assert merge_graph_hits(["a"], ["b", "c"], cap=2) == ["a", "b"]


def test_graph_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_GRAPH_ENABLED", "1")
    assert graph_enabled() is True
    monkeypatch.setenv("KNOWLEDGE_GRAPH_ENABLED", "0")
    assert graph_enabled() is False
