"""Unit tests for the SSE liveness subscriber (push-based connector liveness)."""

import threading
import time

import httpx
import pytest

from minder.core.modules import liveness
from minder.core.modules.registry import (
    ConnectorState, RECONCILE_FAIL_LIMIT, get_registry, reset_registry_for_tests,
)


class _FakeStream:
    """Stand-in for ``httpx.stream(...)`` used as a context manager."""

    def __init__(self, lines, *, raise_on_enter=False):
        self._lines = lines
        self._raise = raise_on_enter

    def __enter__(self):
        if self._raise:
            raise httpx.ConnectError("boom")
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for line in self._lines:
            yield line


@pytest.fixture()
def reg(monkeypatch, tmp_path):
    reset_registry_for_tests()
    monkeypatch.setenv("MINDER_MODULES_DIR", str(tmp_path))
    monkeypatch.setattr(liveness, "BACKOFF_START_SEC", 0.01)
    monkeypatch.setattr(liveness, "BACKOFF_MAX_SEC", 0.01)
    r = get_registry()
    r.register_connector(name="m", connector_url="http://m:9200")
    return r


def _run_worker(sub, name, url, hold=0.05):
    """Run one worker briefly in a thread, then stop it cleanly."""
    wstop = threading.Event()
    t = threading.Thread(target=sub._worker, args=(name, url, wstop), daemon=True)
    t.start()
    time.sleep(hold)
    wstop.set()
    t.join(timeout=2.0)
    return t


def test_worker_bootstraps_and_refreshes_liveness(reg, monkeypatch):
    """An open stream bootstraps tools once and each line refreshes liveness."""
    touched = []
    monkeypatch.setattr(reg, "touch_connector",
                        lambda name: touched.append(name) or True)

    lines = [b": ok", b": ping", b'data: {"type":"x"}']
    monkeypatch.setattr(liveness.httpx, "stream",
                        lambda *a, **k: _FakeStream(lines))

    boots = []
    sub = liveness.ConnectorLivenessSubscriber(bootstrap=lambda n: boots.append(n))
    _run_worker(sub, "m", "http://m:9200")

    assert boots, "bootstrap must run on (re)connect"
    assert touched, "each streamed line must refresh liveness"
    # A comment keepalive and a data envelope both count as proof of life.
    assert len(touched) >= 3


def test_worker_hits_correct_events_url(reg, monkeypatch):
    seen = {}
    monkeypatch.setattr(reg, "touch_connector", lambda name: True)

    def fake_stream(method, url, **k):
        seen["url"] = url
        return _FakeStream([b": ok"])

    monkeypatch.setattr(liveness.httpx, "stream", fake_stream)
    sub = liveness.ConnectorLivenessSubscriber()
    _run_worker(sub, "m", "http://m:9200")
    assert seen["url"] == "http://m:9200/connector/stream"


def test_worker_records_failure_and_reconnects_on_error(reg, monkeypatch):
    """A stream that won't connect trips liveness failures until DOWN."""
    monkeypatch.setattr(liveness.httpx, "stream",
                        lambda *a, **k: _FakeStream([], raise_on_enter=True))
    sub = liveness.ConnectorLivenessSubscriber()
    # Long enough for several retry cycles at the tiny test backoff.
    _run_worker(sub, "m", "http://m:9200", hold=0.2)

    rec = reg.connector("m")
    assert rec.fail_count >= 1 or rec.state is ConnectorState.DOWN


def test_worker_exits_when_connector_deregistered(reg, monkeypatch):
    """If the connector vanishes mid-stream, the worker stops (touch -> False)."""
    monkeypatch.setattr(reg, "touch_connector", lambda name: False)
    monkeypatch.setattr(liveness.httpx, "stream",
                        lambda *a, **k: _FakeStream([b": ok", b": ping"]))
    sub = liveness.ConnectorLivenessSubscriber()

    wstop = threading.Event()
    t = threading.Thread(target=sub._worker, args=("m", "http://m:9200", wstop), daemon=True)
    t.start()
    t.join(timeout=1.0)  # must exit on its own without wstop being set
    assert not t.is_alive(), "worker should exit when touch_connector returns False"


def test_supervisor_spawns_one_worker_per_connector(reg, monkeypatch):
    """The supervisor keeps a worker set matching the registry."""
    monkeypatch.setattr(reg, "touch_connector", lambda name: True)
    # Block forever inside the stream so the worker stays alive for inspection.
    started = threading.Event()

    class _Blocking(_FakeStream):
        def iter_lines(self):
            started.set()
            while True:
                time.sleep(0.01)

    monkeypatch.setattr(liveness.httpx, "stream", lambda *a, **k: _Blocking([]))
    reg.register_connector(name="m2", connector_url="http://m2:9200")

    sub = liveness.ConnectorLivenessSubscriber()
    sub.start()
    try:
        started.wait(timeout=1.0)
        time.sleep(0.05)
        assert set(sub._workers) == {"m", "m2"}
    finally:
        sub.stop()
    assert sub._workers == {}
