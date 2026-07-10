"""Remote proxy tools merge into the registry; corpus stays protected."""
from __future__ import annotations

from atria.core.skill_tools import SkillToolContext, ToolSpec


def test_build_remote_specs_produces_named_proxy_tool():
    from atria.core.modules import remote

    class _Svc:
        connector_url = "http://mc:9200"
        health_path = "/connector/health"
        tools = [{"name": "maintenance_copilot_query", "description": "q",
                  "parameters": {"type": "object"}}]

    class _Manifest:
        service = _Svc()

    class _Mod:
        name = "maintenance_copilot"
        manifest = _Manifest()

    specs = remote.build_remote_tool_specs(SkillToolContext(), [_Mod()])
    by_name = {s.name: s for s in specs}
    assert "maintenance_copilot_query" in by_name
    assert isinstance(by_name["maintenance_copilot_query"], ToolSpec)


def test_core_hardcodes_no_protected_paths():
    # Generic: core ships no module-specific corpus paths — modules declare
    # their own (see test below).
    from atria.models.config import _default_protected_paths

    assert _default_protected_paths() == []


def test_module_declared_protected_paths_become_globs():
    from atria.core.modules import store

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
    from atria.core.modules import store

    class _Mod:
        name = "plain"
        manifest = None

    assert store.module_protected_paths([_Mod()]) == []
