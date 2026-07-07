"""Integration tests for the pg helper and Qdrant dense index."""

import os

import httpx
import pytest

from atria.core.context_engineering.search import pg
from atria.core.context_engineering.search.dense import DenseIndex


def _pg_available() -> bool:
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        pg.fetch_all("SELECT 1 AS one")
        return True
    except Exception:
        return False


def _qdrant_available() -> bool:
    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    try:
        return httpx.get(f"{url}/collections", timeout=2.0).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(), reason="needs live Postgres via DATABASE_URL")
def test_pg_roundtrip():
    pg.execute("DROP TABLE IF EXISTS _search_pg_test")
    pg.execute("CREATE TABLE _search_pg_test(id text primary key, val int)")
    pg.execute("INSERT INTO _search_pg_test VALUES ($1, $2)", ["a", 1])
    rows = pg.fetch_all("SELECT id, val FROM _search_pg_test WHERE val = $1", [1])
    assert rows == [{"id": "a", "val": 1}]
    pg.execute("DROP TABLE _search_pg_test")


@pytest.mark.skipif(not _qdrant_available(), reason="needs live Qdrant")
def test_dense_index_upsert_query_and_filter():
    from qdrant_client import models

    idx = DenseIndex("_search_dense_test")
    idx.ensure(dim=3)
    idx.upsert(
        ids=["x", "y"],
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        payloads=[{"kind": "a"}, {"kind": "b"}],
    )
    hits = idx.query([1.0, 0.0, 0.0], limit=2)
    assert hits[0][0] == "x"
    only_b = idx.query(
        [1.0, 0.0, 0.0],
        query_filter=models.Filter(
            must=[models.FieldCondition(key="kind", match=models.MatchValue(value="b"))]
        ),
        limit=2,
    )
    assert [h[0] for h in only_b] == ["y"]
    # idempotency: re-upsert same ids does not duplicate points
    idx.upsert(ids=["x"], vectors=[[1.0, 0.0, 0.0]], payloads=[{"kind": "a"}])
    assert len(idx.query([1.0, 0.0, 0.0], limit=10)) == 2
    # delete removes exactly the requested point, leaving the rest findable
    idx.delete(["y"])
    remaining = idx.query([1.0, 0.0, 0.0], limit=10)
    assert len(remaining) == 1
    assert remaining[0][0] == "x"
    # delete on an empty list is a no-op
    idx.delete([])
    assert len(idx.query([1.0, 0.0, 0.0], limit=10)) == 1
