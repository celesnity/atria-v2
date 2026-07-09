"""ai_workspace -> EK adapter: lazy import, fail-soft, correct metadata mapping."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_index_document_calls_ingest_api_with_mapped_args(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_1")
    calls = {}
    fake = types.ModuleType("ingest_api")
    fake.ingest_document = lambda **kw: calls.update(kw) or {"chunks_indexed": 1}
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    ok = ek_index.index_document(
        doc_id="DOC900", title="Tiêu đề", dept_code="ENG",
        classification="Internal", text="nội dung", owner="U004",
    )
    assert ok is True
    assert calls["doc_id"] == "DOC900" and calls["department"] == "ENG"
    assert calls["classification"] == "Internal" and calls["owner"] == "U004"
    assert calls["text"] == "nội dung"


def test_index_document_returns_false_on_error(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_2")
    fake = types.ModuleType("ingest_api")

    def boom(**kw):
        raise RuntimeError("qdrant down")

    fake.ingest_document = boom
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    assert ek_index.index_document(
        doc_id="DOC900", title="t", dept_code="ENG",
        classification="Internal", text="x", owner="U004",
    ) is False


def test_remove_document_fail_soft(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_3")
    fake = types.ModuleType("ingest_api")

    def boom(**kw):
        raise RuntimeError("x")

    fake.remove_document = boom
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    assert ek_index.remove_document("DOC900") is False


def test_remove_document_forwards_doc_id(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_4")
    got = {}
    fake = types.ModuleType("ingest_api")
    fake.remove_document = lambda **kw: got.update(kw) or 1
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    assert ek_index.remove_document("DOC900") is True
    assert got["doc_id"] == "DOC900"


def test_reindex_forwards_docs(monkeypatch):
    ek_index = _load("ek_index", "aiw_ekidx_5")
    got = {}
    fake = types.ModuleType("ingest_api")
    fake.reindex_documents = lambda docs, **kw: got.update({"n": len(docs)}) or {"chunks_indexed": 1}
    monkeypatch.setattr(ek_index, "_api", lambda: fake)
    docs = [{"doc_id": "DOCA", "title": "t", "department": "ENG",
             "classification": "Internal", "text": "a b"}]
    assert ek_index.reindex(docs) is True
    assert got["n"] == 1
