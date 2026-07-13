"""Embedder unit tests (transport mocked) plus an opt-in live smoke test."""

import os

import pytest

from minder.core.context_engineering.search.embedder import Embedder


class _FakeResponse:
    def __init__(self, n: int):
        self._n = n

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": [{"index": i, "embedding": [float(i), 1.0]} for i in range(self._n)]}


def test_embed_batches_and_preserves_order(monkeypatch):
    calls: list[int] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(len(json["input"]))
        return _FakeResponse(len(json["input"]))

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = Embedder(model="m", base_url="http://x/v1", api_key="k")
    vectors = emb.embed([f"t{i}" for i in range(70)])  # batch size 64 -> 2 calls
    assert len(vectors) == 70
    assert calls == [64, 6]
    assert vectors[0] == [0.0, 1.0]


def test_embed_empty_returns_empty():
    emb = Embedder(model="m", base_url="http://x/v1", api_key="k")
    assert emb.embed([]) == []


@pytest.mark.skipif(
    not (os.environ.get("SEARCH_EMBED_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="needs an embedding API key",
)
def test_embed_live_smoke():
    emb = Embedder()
    vecs = emb.embed(["quán cà phê yên tĩnh"])
    assert len(vecs) == 1
    assert len(vecs[0]) > 100
