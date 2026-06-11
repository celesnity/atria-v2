import pytest


@pytest.mark.asyncio
async def test_get_pool_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import atria.db.connection as conn_mod

    conn_mod._pool = None  # reset cached pool so the env-var check runs
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        await conn_mod.get_pool()


def test_run_sync_executes_coroutine():
    from atria.db.sync import run_sync

    async def _add(a, b):
        return a + b

    assert run_sync(_add(2, 3)) == 5
