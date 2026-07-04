"""Unit tests for S5 advisory gating + S2 shared job store."""
from __future__ import annotations

from types import SimpleNamespace

from atria.core.orchestration.gating import assess_heavy_path, model_is_strong
from atria.core.orchestration.job_store import SUBAGENT_PREFIX, JobStore


# --------------------------------------------------------------------------- #
# S5 — strong-model heuristic + advisory text
# --------------------------------------------------------------------------- #
def test_model_is_strong():
    assert model_is_strong("claude-opus-4-6")
    assert model_is_strong("gpt-5.4")
    assert model_is_strong("gemini-3-pro")
    assert model_is_strong("deepseek-v4-pro")
    assert not model_is_strong("gemini-3-flash")
    assert not model_is_strong("gpt-4o-mini")
    assert not model_is_strong("hosted_vllm/Qwen/Qwen3.5-35B-A3B-FP8")
    assert not model_is_strong(None)


def test_assess_heavy_path_advises_only_for_strong():
    assert assess_heavy_path(SimpleNamespace(model="claude-opus-4-6")).startswith("advisory:")
    assert assess_heavy_path(SimpleNamespace(model="gemini-3-flash")) == ""
    assert assess_heavy_path(SimpleNamespace(model=None)) == ""


# --------------------------------------------------------------------------- #
# S2 — shared prefix-namespaced JobStore
# --------------------------------------------------------------------------- #
def test_job_store_prefixes_distinct():
    assert SUBAGENT_PREFIX == "atria:sajob:"


class _FakeRedis:
    def __init__(self):
        self.kv = {}

    async def set(self, k, v, ex=None):
        self.kv[k] = v

    async def get(self, k):
        return self.kv.get(k)

    async def delete(self, k):
        self.kv.pop(k, None)


def test_job_store_namespaces_by_prefix():
    import asyncio

    r = _FakeRedis()
    pjs = JobStore(r, SUBAGENT_PREFIX)
    djs = JobStore(r, "atria:other:")

    async def go():
        await pjs.save("x", {"k": "p"}, ttl=10)
        await djs.save("x", {"k": "d"}, ttl=10)
        # Same job_id, different namespaces -> no collision.
        assert (await pjs.load("x"))["k"] == "p"
        assert (await djs.load("x"))["k"] == "d"
        assert set(r.kv.keys()) == {"atria:sajob:x", "atria:other:x"}
        await pjs.delete("x")
        assert await pjs.load("x") is None
        assert await djs.load("x") is not None

    asyncio.run(go())


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
