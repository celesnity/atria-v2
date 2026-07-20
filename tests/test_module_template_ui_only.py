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


def test_core_does_not_start_legacy_connector_runtime() -> None:
    """UI-only remotes must not revive connector polling or SSE liveness."""
    server = (REPO_ROOT / "minder/web/server.py").read_text()

    assert "start_connector_reconciler(" not in server
    assert "start_liveness_subscriber(" not in server
    assert "module_connector_router" not in server


def test_module_picker_does_not_poll_connector_health() -> None:
    """A federation remote is discovered from its manifest, not a connector."""
    breadcrumb = (REPO_ROOT / "web-ui/src/components/Layout/ModuleBreadcrumb.tsx").read_text()

    assert "useModuleHealth" not in breadcrumb
    assert "ModuleHealthDot" not in breadcrumb
