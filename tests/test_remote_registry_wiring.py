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


def test_default_protected_paths_cover_backend_corpus():
    from atria.models.config import _default_protected_paths

    patterns = [p.pattern for p in _default_protected_paths()]
    assert "modules/*/backend/sample_manuals" in patterns
    # The pre-existing location stays protected too (defense in depth during migration).
    assert "modules/*/sample_manuals" in patterns
