"""Watchdog-based observer for ``~/.minder/modules``.

On any create/modify/delete of ``SKILL.md`` or ``script.py`` under a module
folder, reloads that module in the registry and invokes ``on_change(name)``.
Per-module reloads are debounced (200 ms) to coalesce editor-save bursts, and
all ``on_change`` notifications are further coalesced through a global timer
(500 ms) so bulk operations (e.g. regenerating many modules at once) produce a
single notification rather than one per module.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from minder.core.modules.registry import ModuleRegistry, get_registry
from minder.core.modules.remote import RemoteConnector

logger = logging.getLogger(__name__)

DEBOUNCE_SEC = 0.2
NOTIFY_DEBOUNCE_SEC = 0.5


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "ModuleWatcher") -> None:
        self._w = watcher

    def _module_name_for(self, raw_path: str) -> Optional[str]:
        try:
            p = Path(raw_path).resolve()
            rel = p.relative_to(self._w.registry.root.resolve())
        except (ValueError, OSError):
            return None
        parts = rel.parts
        if len(parts) < 2:
            return None
        # Ignore atomic-write temp files and python bytecode noise.
        leaf = parts[-1]
        if leaf.startswith(".tmp-") or leaf.endswith(".pyc"):
            return None
        if "__pycache__" in parts:
            return None
        return parts[0]

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            # A deleted folder fires per-file delete events for its children, which we
            # already pick up via _module_name_for. Folder events themselves are noisy.
            return
        # For "moved" events (e.g., atomic ``os.replace`` from ``.tmp-SKILL.md`` to
        # ``SKILL.md``), the relevant final path is ``dest_path``. ``src_path`` is
        # the now-gone temp file. Check both so atomic writes are picked up.
        for raw in (getattr(event, "dest_path", "") or "", event.src_path):
            if not raw:
                continue
            name = self._module_name_for(raw)
            if name:
                self._w.schedule(name)
                return


class ModuleWatcher:
    """Filesystem observer that keeps a ``ModuleRegistry`` in sync."""

    def __init__(self, registry: ModuleRegistry, on_change: Callable[[str], None] | None = None):
        self.registry = registry
        self._on_change = on_change
        self._observer: Optional[Observer] = None
        self._timers: Dict[str, threading.Timer] = {}
        self._timers_lock = threading.Lock()
        self._notify_timer: Optional[threading.Timer] = None
        self._pending_notify: set[str] = set()
        self._notify_lock = threading.Lock()

    def start(self) -> None:
        self.registry.root.mkdir(parents=True, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self.registry.root), recursive=True)
        self._observer.start()
        logger.info("module watcher started on %s", self.registry.root)

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        with self._timers_lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()
        with self._notify_lock:
            if self._notify_timer is not None:
                self._notify_timer.cancel()
                self._notify_timer = None
            self._pending_notify.clear()

    def schedule(self, name: str) -> None:
        """Debounced reload-and-notify for ``name``."""
        with self._timers_lock:
            existing = self._timers.get(name)
            if existing is not None:
                existing.cancel()
            t = threading.Timer(DEBOUNCE_SEC, self._fire, args=(name,))
            t.daemon = True
            self._timers[name] = t
            t.start()

    def _fire(self, name: str) -> None:
        try:
            self.registry.reload_one(name)
        except Exception as e:  # never let watcher crash the server
            logger.warning("module reload failed for %s: %s", name, e)
            return
        if self._on_change is None:
            return
        with self._notify_lock:
            self._pending_notify.add(name)
            if self._notify_timer is not None:
                self._notify_timer.cancel()
            t = threading.Timer(NOTIFY_DEBOUNCE_SEC, self._fire_notify)
            t.daemon = True
            self._notify_timer = t
            t.start()

    def _fire_notify(self) -> None:
        with self._notify_lock:
            names = list(self._pending_notify)
            self._pending_notify.clear()
            self._notify_timer = None
        if self._on_change is None or not names:
            return
        # Frontend only triggers a refresh on this event, so a single notification
        # per batch is sufficient. Pass the first name (or "*" for multi) so any
        # name-aware consumer still gets a signal without N broadcasts.
        payload = names[0] if len(names) == 1 else "*"
        try:
            self._on_change(payload)
        except Exception as e:
            logger.warning("module on_change callback failed for %s: %s", payload, e)


_WATCHER: Optional[ModuleWatcher] = None


def start_global_watcher(
    on_change: Callable[[str], None] | None = None,
) -> ModuleWatcher:
    """Start the process-wide watcher (idempotent)."""
    global _WATCHER
    if _WATCHER is not None:
        return _WATCHER

    _WATCHER = ModuleWatcher(get_registry(), on_change=on_change)
    _WATCHER.start()
    return _WATCHER


def stop_global_watcher() -> None:
    global _WATCHER
    if _WATCHER is not None:
        _WATCHER.stop()
        _WATCHER = None


RECONCILE_INTERVAL_SEC = 5.0


class ConnectorReconciler:
    """Poll every registered connector: refresh live tool schemas + liveness."""

    def __init__(self, on_change: Optional[Callable[[], None]] = None) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_change = on_change

    def reconcile_once(self, name: Optional[str] = None) -> None:
        reg = get_registry()
        before = reg.version
        for rec in reg.connector_records():
            if name is not None and rec.name != name:
                continue
            conn = RemoteConnector(rec.name, rec.connector_url)
            manifest = None
            try:
                manifest = conn.fetch_manifest()
            except Exception:  # noqa: BLE001 — network failure == unhealthy
                manifest = None
            if manifest is None:
                reg.record_health_failure(rec.name)
                continue
            health = conn.health()
            if not health.get("ok", False):
                # Unreachable / error payload — count it a liveness failure.
                reg.record_health_failure(rec.name)
                continue
            if health.get("ready") is False:
                # Alive but not serving yet — keep tools out of the catalog,
                # but do NOT count it a health failure.
                continue
            tools = manifest.get("tools") or []
            context = manifest.get("context") if isinstance(manifest.get("context"), dict) else {}
            reg.mark_connector_ready(rec.name, tools, context=context)
        if reg.version != before and self._on_change is not None:
            try:
                self._on_change()
            except Exception:  # noqa: BLE001 — broadcast failure must not kill the reconcile loop
                logger.warning("ConnectorReconciler on_change callback failed")

    def _run(self) -> None:
        while not self._stop.wait(RECONCILE_INTERVAL_SEC):
            try:
                self.reconcile_once()
            except Exception:  # noqa: BLE001 — never let the loop die
                logger.exception("connector reconcile pass failed")

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="connector-reconciler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


_RECONCILER: Optional[ConnectorReconciler] = None


def start_connector_reconciler(on_change: Optional[Callable[[], None]] = None) -> None:
    global _RECONCILER
    if _RECONCILER is None:
        _RECONCILER = ConnectorReconciler(on_change=on_change)
        _RECONCILER.start()


def stop_connector_reconciler() -> None:
    global _RECONCILER
    if _RECONCILER is not None:
        _RECONCILER.stop()
        _RECONCILER = None


def kick_reconcile(name: str) -> None:
    """Reconcile a single connector immediately (called from the register route)."""
    if _RECONCILER is not None:
        _RECONCILER.reconcile_once(name)
