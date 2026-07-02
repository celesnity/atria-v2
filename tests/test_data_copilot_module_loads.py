"""The data_copilot module is well-formed and loads via the module store."""

from __future__ import annotations

import json
from pathlib import Path

from atria.core.modules import store

_ROOT = Path(__file__).resolve().parent.parent / "modules"


def test_module_reads_with_manifest_and_description():
    mod = store.read_module(_ROOT, "data_copilot")
    assert mod.name == "data_copilot"
    assert "data" in mod.description.lower()
    assert mod.manifest is not None
    assert mod.manifest.display_name == "Data Copilot"
    # dashboard declared
    assert mod.manifest.dashboard is not None


def test_manifest_json_is_valid_and_has_activity_labels():
    raw = json.loads((_ROOT / "data_copilot" / "manifest.json").read_text())
    assert raw["activity"]["actions"]["analyze"]["running"]
    assert raw["activity"]["actions"]["profile"]["running"]


def test_key_scripts_present():
    scripts = _ROOT / "data_copilot" / "scripts"
    for name in [
        "config",
        "client",
        "profile",
        "guardrails",
        "sandbox",
        "generate",
        "verify",
        "report",
        "audit",
        "copilot",
    ]:
        assert (scripts / f"{name}.py").is_file(), name
