"""BM25 tokenizer + sparse-vector builder tests (pure, no Qdrant)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_tokenize_lowercases_strips_punct_keeps_vietnamese():
    bm25 = _load("bm25", "ek_bm25_tok")
    assert bm25.tokenize("Chính  sách,  Nghỉ Phép!") == ["chính", "sách", "nghỉ", "phép"]
    assert bm25.tokenize("") == []


def test_term_id_stable_and_uint32():
    bm25 = _load("bm25", "ek_bm25_tid")
    assert bm25.term_id("nghỉ") == bm25.term_id("nghỉ")
    assert bm25.term_id("nghỉ") != bm25.term_id("phép")
    assert 0 <= bm25.term_id("x") <= 0xFFFFFFFF


def test_doc_sparse_bm25_weights():
    bm25 = _load("bm25", "ek_bm25_doc")
    # tokens x,x,y ; avgdl=3 ; k1=1.5,b=0.75 -> denom_norm = 1.5*(0.25+0.75*3/3)=1.5
    idx, val = bm25.doc_sparse(["x", "x", "y"], avgdl=3.0)
    weights = dict(zip(idx, val))
    assert round(weights[bm25.term_id("x")], 4) == round(2 * 2.5 / (2 + 1.5), 4)  # ~1.4286
    assert round(weights[bm25.term_id("y")], 4) == round(1 * 2.5 / (1 + 1.5), 4)  # 1.0
    assert bm25.doc_sparse([], avgdl=3.0) == ([], [])


def test_query_sparse_unique_terms_value_one():
    bm25 = _load("bm25", "ek_bm25_q")
    idx, val = bm25.query_sparse(["x", "x", "y"])
    assert sorted(idx) == sorted({bm25.term_id("x"), bm25.term_id("y")})
    assert val == [1.0, 1.0]


def test_average_length():
    bm25 = _load("bm25", "ek_bm25_avg")
    assert bm25.average_length(["a b c", "a b"]) == 2.5
    assert bm25.average_length([]) == 1.0
