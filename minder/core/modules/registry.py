"""In-memory module registry. Versioned so prompt builders can detect changes."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from minder.core.modules import store
from minder.core.modules.deps import install_module_deps
from minder.core.modules.store import Module, ModuleNotFound
from minder.core.paths import minder_dir

logger = logging.getLogger(__name__)

RECONCILE_FAIL_LIMIT = 3


class ConnectorState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    DOWN = "down"


@dataclass
class ConnectorRecord:
    name: str
    connector_url: str
    remote_entry: Optional[str] = None
    api_base: Optional[str] = None
    state: ConnectorState = ConnectorState.PENDING
    tools: List[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    fail_count: int = 0
    last_seen: float = 0.0


def load_disabled_modules() -> set[str]:
    """Names to exclude from discovery, read from ``MINDER_DISABLED_MODULES``.

    Comma- or whitespace-separated list of module folder names, or ``*`` /
    ``all`` to disable every module. This is a true kill switch — disabled
    modules never enter the registry, so they stay off the prompt catalog,
    subagent routing, and dependency install — while their folder remains
    untouched on disk. Empty/unset means nothing is disabled.
    """
    raw = os.environ.get("MINDER_DISABLED_MODULES", "")
    return {tok for tok in re.split(r"[,\s]+", raw) if tok}


def _all_modules_disabled(disabled: set[str]) -> bool:
    """True when the env requests disabling every module (``*`` or ``all``)."""
    return "*" in disabled or "all" in disabled


def resolve_modules_root() -> Path:
    """Discover the modules directory.

    Priority:
      1. ``MINDER_MODULES_DIR`` env var (absolute or relative to CWD).
      2. ``<cwd>/modules`` if it exists — top-level, source-tracked.
      3. ``<cwd>/.minder/modules`` (project-local hidden convention).
      4. ``~/.minder/modules`` (legacy user-global fallback).

    The resolved directory is created on first use.
    """
    env = os.environ.get("MINDER_MODULES_DIR")
    if env:
        return Path(env).expanduser().resolve()
    cwd_modules = Path.cwd() / "modules"
    if cwd_modules.is_dir():
        return cwd_modules.resolve()
    cwd_project = Path.cwd() / ".minder"
    if cwd_project.is_dir():
        return (cwd_project / "modules").resolve()
    return (minder_dir() / "modules").resolve()


class ModuleRegistry:
    """Thread-safe in-memory registry of file-based modules."""

    def __init__(self, root: Path):
        self.root = root
        self._modules: Dict[str, Module] = {}
        self._connectors: Dict[str, ConnectorRecord] = {}
        self._version: int = 0
        self._lock = threading.Lock()

    @property
    def version(self) -> int:
        return self._version

    def load_all(self) -> None:
        """Replace contents with everything currently on disk. Bumps version."""
        disabled = load_disabled_modules()
        skip_all = _all_modules_disabled(disabled)
        with self._lock:
            modules = (
                []
                if skip_all
                else [m for m in store.list_modules(self.root) if m.name not in disabled]
            )
            for m in modules:
                install_module_deps(m.dir)
            self._modules = {m.name: m for m in modules}
            self._version += 1
        logger.info(
            "module registry: loaded %d module(s) (v=%d, %d disabled via env)",
            len(self._modules),
            self._version,
            len(disabled),
        )

    def reload_one(self, name: str) -> None:
        """Reload a single module from disk. If gone or disabled, remove it. Bumps version."""
        disabled = load_disabled_modules()
        if name in disabled or _all_modules_disabled(disabled):
            self.remove(name)
            return
        with self._lock:
            try:
                module = store.read_module(self.root, name)
                install_module_deps(module.dir)
                self._modules[name] = module
            except ModuleNotFound:
                self._modules.pop(name, None)
            self._version += 1

    def remove(self, name: str) -> None:
        with self._lock:
            self._modules.pop(name, None)
            self._version += 1

    def all(self) -> List[Module]:
        with self._lock:
            return [self._modules[n] for n in sorted(self._modules)]

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._modules)

    def get(self, name: str) -> Module:
        with self._lock:
            return self._modules[name]

    def register_connector(
        self,
        *,
        name: str,
        connector_url: str,
        remote_entry: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> None:
        """Runtime announce: ensure a connector record exists, bumping version
        only on a real change. A repeat announce/heartbeat with the same URL just
        refreshes ``last_seen`` — it must not demote a READY connector back to
        PENDING or churn the version (the reconciler owns state transitions)."""
        with self._lock:
            rec = self._connectors.get(name)
            if rec is not None and rec.connector_url == connector_url:
                rec.remote_entry = remote_entry
                rec.api_base = api_base
                rec.last_seen = time.time()
                return
            if rec is None:
                rec = ConnectorRecord(name=name, connector_url=connector_url)
                self._connectors[name] = rec
            rec.connector_url = connector_url
            rec.remote_entry = remote_entry
            rec.api_base = api_base
            rec.state = ConnectorState.PENDING
            rec.fail_count = 0
            rec.last_seen = time.time()
            self._version += 1

    def mark_connector_ready(
        self, name: str, tools: List[dict], context: Optional[dict] = None
    ) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None:
                return
            ctx_block = context if isinstance(context, dict) else {}
            changed = (
                rec.state != ConnectorState.READY
                or rec.tools != tools
                or rec.context != ctx_block
            )
            rec.state = ConnectorState.READY
            rec.tools = list(tools)
            rec.context = ctx_block
            rec.fail_count = 0
            rec.last_seen = time.time()
            if changed:
                self._version += 1

    def mark_connector_down(self, name: str) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None or rec.state == ConnectorState.DOWN:
                return
            rec.state = ConnectorState.DOWN
            self._version += 1

    def record_health_failure(self, name: str) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None:
                return
            rec.fail_count += 1
            over_limit = rec.fail_count >= RECONCILE_FAIL_LIMIT
        if over_limit:
            self.mark_connector_down(name)

    def connector(self, name: str) -> Optional[ConnectorRecord]:
        """Return the runtime connector record for ``name`` (or ``None``).

        This is the self-registration store, distinct from the on-disk guidance
        ``Module`` (``get``). A module that announced at runtime lives here even
        when its static ``manifest.service`` block is absent.
        """
        with self._lock:
            return self._connectors.get(name)

    def connector_records(self) -> List[ConnectorRecord]:
        with self._lock:
            return [self._connectors[n] for n in sorted(self._connectors)]

    def connector_tools(self, name: str) -> List[dict]:
        with self._lock:
            rec = self._connectors.get(name)
            return list(rec.tools) if rec and rec.state == ConnectorState.READY else []

    def live_service_modules(self) -> List[Module]:
        """Guidance Modules whose connector is READY (agent tool-builder input)."""
        with self._lock:
            ready = {n for n, r in self._connectors.items() if r.state == ConnectorState.READY}
            return [self._modules[n] for n in sorted(self._modules) if n in ready]


_GLOBAL: ModuleRegistry | None = None


def get_registry() -> ModuleRegistry:
    """Return the process-wide registry.

    Root is resolved by :func:`resolve_modules_root` — project ``.minder/modules``
    takes precedence over the user-global ``~/.minder/modules``.
    """
    global _GLOBAL
    if _GLOBAL is None:
        root = resolve_modules_root()
        root.mkdir(parents=True, exist_ok=True)
        logger.info("module registry rooted at: %s", root)
        _GLOBAL = ModuleRegistry(root)
        _GLOBAL.load_all()
    return _GLOBAL


def reset_registry_for_tests() -> None:
    """Test helper: clear the process-wide registry singleton."""
    global _GLOBAL
    _GLOBAL = None
