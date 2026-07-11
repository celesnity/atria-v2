"""Collision-proof sibling loader for enterprise_knowledge scripts.

Both ``enterprise_knowledge`` and ``maintenance_copilot`` ship bare-named
scripts (``graph_store.py``, ``index_store.py``, ``acl.py`` …). A plain
``import graph_store`` resolves through ``sys.modules`` by that bare name, so
when both modules are imported into a single interpreter (e.g. the pytest
suite collects both modules' tests) whichever loads first wins the name and the
other silently binds to the wrong file. At runtime each module runs as its own
subprocess so the clash never shows, but in-process it does.

``sibling()`` loads an EK script under an ``_ek_``-namespaced ``sys.modules``
key from THIS directory, so EK always binds to its own file regardless of what
occupies the bare name. Use it for every intra-module import:

    from _bootstrap import sibling

    graph_store = sibling("graph_store")
    User = sibling("identity").User
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def sibling(name: str) -> ModuleType:
    """Import the EK script ``<name>.py`` from this directory under a namespaced
    key, immune to bare-name collisions with other modules' scripts."""
    key = f"_ek_{name}"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load EK sibling module {name!r} from {_HERE}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod
