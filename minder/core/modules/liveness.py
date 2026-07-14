"""SSE-based connector liveness — push instead of poll.

Each registered module connector exposes ``GET /connector/events`` (an SSE
stream of event envelopes, with a ``: ping`` keepalive every ~15 s). Rather than
HTTP-polling ``/connector/health`` on a timer, the host holds ONE long-lived
stream per connector: an open stream is itself proof of life, and every line
(``: ok`` / ``: ping`` / ``data:``) refreshes liveness in-memory — no request, no
``modules.changed`` broadcast. A dropped stream is a liveness failure; the worker
reconnects with exponential backoff.

The polling :class:`ConnectorReconciler` stays on as a slow safety-net: it
bootstraps tools/manifest and covers the window before a stream first connects or
while it is reconnecting. This module only supplies the realtime liveness layer.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional

import httpx

from minder.core.modules.registry import get_registry

logger = logging.getLogger(__name__)

# How often the supervisor re-syncs its worker set to the registry (picks up
# newly self-registered connectors, drops deregistered ones). Cheap in-memory
# scan — no network — so this can be brisk.
SYNC_INTERVAL_SEC = 5.0

# Reconnect backoff bounds after a stream drops.
BACKOFF_START_SEC = 1.0
BACKOFF_MAX_SEC = 30.0

# httpx read timeout for a single SSE line. The connector sends a keepalive every
# ~15 s, so a read gap well past that means the stream is dead — trip a reconnect.
STREAM_READ_TIMEOUT_SEC = 45.0


class ConnectorLivenessSubscriber:
    """Supervises one SSE liveness worker per registered connector."""

    def __init__(
        self,
        bootstrap: Optional[Callable[[str], None]] = None,
    ) -> None:
        """``bootstrap(name)`` is called once each time a stream (re)connects, to
        (re)load the connector's manifest/tools and mark it READY — normally
        ``ConnectorReconciler.reconcile_once``."""
        self._bootstrap = bootstrap
        self._stop = threading.Event()
        self._supervisor: Optional[threading.Thread] = None
        # name -> (thread, per-worker stop Event)
        self._workers: Dict[str, tuple[threading.Thread, threading.Event]] = {}

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._supervisor is not None:
            return
        self._stop.clear()
        self._supervisor = threading.Thread(
            target=self._supervise, name="connector-liveness-supervisor", daemon=True
        )
        self._supervisor.start()

    def stop(self) -> None:
        self._stop.set()
        for _, wstop in list(self._workers.values()):
            wstop.set()
        for thread, _ in list(self._workers.values()):
            thread.join(timeout=2.0)
        self._workers.clear()
        if self._supervisor is not None:
            self._supervisor.join(timeout=2.0)
            self._supervisor = None

    # -- supervisor -----------------------------------------------------------

    def _supervise(self) -> None:
        """Keep exactly one worker alive per registered connector."""
        while not self._stop.wait(0 if not self._workers else SYNC_INTERVAL_SEC):
            try:
                self._sync_workers()
            except Exception:  # noqa: BLE001 — never let the supervisor die
                logger.exception("liveness supervisor sync failed")
            if self._stop.is_set():
                break

    def _sync_workers(self) -> None:
        reg = get_registry()
        wanted = {rec.name: rec.connector_url for rec in reg.connector_records()}

        # Drop workers whose connector is gone or has finished.
        for name in list(self._workers):
            thread, wstop = self._workers[name]
            if name not in wanted or not thread.is_alive():
                wstop.set()
                self._workers.pop(name, None)

        # Spawn workers for newly-seen connectors.
        for name, url in wanted.items():
            if name in self._workers:
                continue
            wstop = threading.Event()
            thread = threading.Thread(
                target=self._worker, args=(name, url, wstop),
                name=f"connector-liveness-{name}", daemon=True,
            )
            self._workers[name] = (thread, wstop)
            thread.start()

    # -- per-connector worker -------------------------------------------------

    def _worker(self, name: str, url: str, wstop: threading.Event) -> None:
        """Hold the ``/connector/events`` stream open; each line = liveness."""
        events_url = f"{url.rstrip('/')}/connector/events"
        backoff = BACKOFF_START_SEC
        reg = get_registry()
        while not (wstop.is_set() or self._stop.is_set()):
            try:
                timeout = httpx.Timeout(STREAM_READ_TIMEOUT_SEC, connect=5.0)
                with httpx.stream("GET", events_url, timeout=timeout) as resp:
                    resp.raise_for_status()
                    # Connected == alive. Bootstrap tools/manifest once per
                    # (re)connect, then let each streamed line refresh liveness.
                    if self._bootstrap is not None:
                        try:
                            self._bootstrap(name)
                        except Exception:  # noqa: BLE001
                            logger.warning("liveness bootstrap failed for %s", name)
                    backoff = BACKOFF_START_SEC
                    for _line in resp.iter_lines():
                        if wstop.is_set() or self._stop.is_set():
                            return
                        # Any line — comment keepalive (": ping") or a "data:"
                        # envelope — proves the connector is alive.
                        if not reg.touch_connector(name):
                            return  # connector deregistered — end this worker
            except Exception:  # noqa: BLE001 — connect/read failure == unhealthy
                reg.record_health_failure(name)
            # Stream ended or errored — wait (interruptibly) then reconnect.
            if wstop.wait(backoff) or self._stop.is_set():
                return
            backoff = min(backoff * 2, BACKOFF_MAX_SEC)


_SUBSCRIBER: Optional[ConnectorLivenessSubscriber] = None


def start_liveness_subscriber(
    bootstrap: Optional[Callable[[str], None]] = None,
) -> None:
    global _SUBSCRIBER
    if _SUBSCRIBER is None:
        _SUBSCRIBER = ConnectorLivenessSubscriber(bootstrap=bootstrap)
        _SUBSCRIBER.start()


def stop_liveness_subscriber() -> None:
    global _SUBSCRIBER
    if _SUBSCRIBER is not None:
        _SUBSCRIBER.stop()
        _SUBSCRIBER = None
