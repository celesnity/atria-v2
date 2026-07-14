"""Unit tests for the result envelope and RRF fusion utilities."""

from minder.core.context_engineering.search.fusion import facet_counts, rrf_fuse, top_margin
from minder.core.context_engineering.search.types import SearchHit, SourceResults


def test_rrf_rewards_items_ranked_high_in_both_lists():
    fused = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]])
    assert fused["a"] > fused["c"]
    assert fused["b"] > fused["d"]
    # a and b appear in both lists; c and d only in one
    assert min(fused["a"], fused["b"]) > max(fused["c"], fused["d"])


def test_rrf_single_list_preserves_order():
    fused = rrf_fuse([["x", "y"]])
    assert fused["x"] > fused["y"]


def test_top_margin():
    assert top_margin([]) is None
    assert top_margin([0.9]) == 1.0  # unrivalled top hit -> max margin
    assert abs(top_margin([0.8, 0.4]) - 0.5) < 1e-9
    assert top_margin([0.5, 0.5]) == 0.0


def test_facet_counts():
    rows = [
        {"category": "cafe", "city": "Hà Nội"},
        {"category": "cafe", "city": "TP.HCM"},
        {"category": "hotel", "city": "TP.HCM"},
    ]
    facets = facet_counts(rows, ["category", "city"])
    assert facets["category"] == {"cafe": 2, "hotel": 1}
    assert facets["city"] == {"TP.HCM": 2, "Hà Nội": 1}


def test_source_results_to_dict_roundtrip():
    hit = SearchHit(id="d1", source="documents", title="T", snippet="s", score=0.5, metadata={})
    res = SourceResults(source="documents", hits=[hit], facets={}, top_margin=1.0, note=None)
    d = res.to_dict()
    assert d["source"] == "documents"
    assert d["hits"][0]["id"] == "d1"
    assert d["top_margin"] == 1.0
    assert "note" not in d  # None fields omitted for token economy
