"""Remote proxy tools merge into the registry; corpus stays protected."""
from __future__ import annotations

from minder.core.skill_tools import SkillToolContext, ToolSpec


def test_build_remote_specs_produces_named_proxy_tool(monkeypatch, tmp_path):
    from minder.core.modules.registry import reset_registry_for_tests, get_registry
    from minder.core.modules.remote import build_remote_tool_specs

    reset_registry_for_tests()
    monkeypatch.setenv("MINDER_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="maintenance_copilot", connector_url="http://mc:9200")
    reg.mark_connector_ready("maintenance_copilot", [{"name": "maintenance_copilot_query",
                                                      "description": "q",
                                                      "parameters": {"type": "object"}}])
    specs = build_remote_tool_specs(SkillToolContext(), reg.live_service_modules())
    by_name = {s.name: s for s in specs}
    assert "maintenance_copilot_query" in by_name
    assert isinstance(by_name["maintenance_copilot_query"], ToolSpec)


def test_build_specs_only_for_ready_connectors(monkeypatch, tmp_path):
    from minder.core.modules.registry import reset_registry_for_tests, get_registry
    from minder.core.modules.remote import build_remote_tool_specs

    reset_registry_for_tests()
    monkeypatch.setenv("MINDER_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="m", connector_url="http://m:9200")
    # PENDING → no specs
    assert build_remote_tool_specs(SkillToolContext(), reg.live_service_modules()) == []
    reg.mark_connector_ready("m", [{"name": "m_q", "parameters": {"type": "object"}}])
    specs = build_remote_tool_specs(SkillToolContext(), reg.live_service_modules())
    # A live connector also gets the module-context reader appended.
    assert [s.name for s in specs] == ["m_q", "read_module_context"]


def test_core_hardcodes_no_protected_paths():
    # Generic: core ships no module-specific corpus paths — modules declare
    # their own (see test below).
    from minder.models.config import _default_protected_paths

    assert _default_protected_paths() == []


def test_module_declared_protected_paths_become_globs():
    from minder.core.modules import store

    class _Manifest:
        protected_paths = [
            {"path": "sample_manuals", "message": "no"},
            {"path": "backend/sample_manuals", "message": "no"},
        ]

    class _Mod:
        name = "maintenance_copilot"
        manifest = _Manifest()

    patterns = [p.pattern for p in store.module_protected_paths([_Mod()])]
    assert "modules/maintenance_copilot/sample_manuals" in patterns
    assert "modules/maintenance_copilot/backend/sample_manuals" in patterns


def test_module_without_protected_paths_yields_none():
    from minder.core.modules import store

    class _Mod:
        name = "plain"
        manifest = None

    assert store.module_protected_paths([_Mod()]) == []
