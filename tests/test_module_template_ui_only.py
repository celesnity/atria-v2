"""Regression coverage for the static module-template dashboard."""

from pathlib import Path

from minder.core.modules import store


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_module_template_is_a_discoverable_static_remote() -> None:
    module = store.read_module(REPO_ROOT / "modules", "module_template")

    assert "UI-only" in module.skill_md
    assert module.manifest is not None
    assert module.manifest.service is None
    assert module.manifest.remote is not None
    assert module.manifest.remote.remote_entry == "http://localhost:9300/dashboard/remoteEntry.js"
