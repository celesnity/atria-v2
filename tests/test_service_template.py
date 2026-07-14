"""Scaffolded service modules must wire the minder-ui-sdk tab contract."""
import json

from minder.core.modules import service_template


def test_files_include_sdk_dashboard_sources():
    files = service_template.files("acme", "demo", port=9400)
    assert "frontend/src/dashboard.tabs.ts" in files
    assert "frontend/src/dashboard.tsx" in files
    assert "frontend/src/DashboardApp.tsx" not in files


def test_vite_config_wires_plugin_and_alias():
    cfg = service_template.frontend_vite_config("acme", 9400)
    assert "minderTabsSync" in cfg
    assert "minder-ui-sdk" in cfg
    assert "./src/dashboard.tsx" in cfg  # exposes the new entry


def test_dashboard_tsx_uses_define_dashboard():
    tsx = service_template.frontend_dashboard_tsx("acme")
    assert "defineDashboard" in tsx
    assert "from 'minder-ui-sdk'" in tsx


def test_tabs_source_exports_plain_data():
    src = service_template.frontend_dashboard_tabs("acme")
    assert "export const TABS" in src


def test_dockerfile_copies_sdk_for_frontend_build():
    df = service_template.backend_dockerfile("acme", 9400)
    assert "COPY minder_ui_sdk /minder_ui_sdk" in df


def test_manifest_declares_dashboard_tabs():
    mf = json.loads(service_template.manifest_json("acme", 9400))
    assert "tabs" in mf["dashboard"]
    assert isinstance(mf["dashboard"]["tabs"], list)
