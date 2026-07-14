"""The enterprise_knowledge module exposes a typed RAG query tool.

Small models fumbled the raw `python knowledge.py query ...` CLI (wrong path,
`--user_id` instead of `--user`, bare-script probes). A structured tool removes
the shell surface. These tests pin the command it builds and that the module is
discovered through the skill-tool loader.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EK = REPO / "modules" / "enterprise_knowledge"


def _load_agent_tools():
    spec = importlib.util.spec_from_file_location(
        "ek_agent_tools_under_test", EK / "agent_tools.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_build_query_cmd_uses_absolute_path_and_correct_flag():
    mod = _load_agent_tools()
    cmd = mod.build_query_cmd("U001", "Chính sách thử việc là gì?")
    # The two mistakes the model kept making must be impossible now:
    assert "--user" in cmd and "--user_id" not in cmd
    knowledge = cmd[1]
    assert knowledge.endswith("knowledge.py")
    assert "scripts" in Path(knowledge).parts  # not the module root
    assert Path(knowledge).is_absolute()
    # Structure: positional question, --synthesize by default.
    assert "query" in cmd and "Chính sách thử việc là gì?" in cmd
    assert "--synthesize" in cmd
    assert cmd[cmd.index("--user") + 1] == "U001"


def test_build_query_cmd_optional_department_and_no_synthesize():
    mod = _load_agent_tools()
    cmd = mod.build_query_cmd("U001", "q", synthesize=False, department="ENG", mode="bm25")
    assert "--synthesize" not in cmd
    assert cmd[cmd.index("--department") + 1] == "ENG"
    assert cmd[cmd.index("--mode") + 1] == "bm25"


def test_handler_rejects_missing_args():
    mod = _load_agent_tools()
    res = mod._run_query(user_id="", question="")
    assert res["success"] is False
    assert "required" in res["error"].lower()


def test_handler_output_is_string_not_dict(monkeypatch):
    # The react loop's compactor runs a regex over tool-result content and needs
    # a STRING. A dict output raised "expected string or buffer" and the whole
    # turn errored out with no answer. Lock the contract: output must be str.
    mod = _load_agent_tools()

    class _FakeProc:
        returncode = 0
        stdout = '{"query": "q", "hits": []}'
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeProc())
    res = mod._run_query(user_id="U001", question="q")
    assert res["success"] is True
    assert isinstance(res["output"], str)


def test_register_exposes_query_tool():
    mod = _load_agent_tools()
    from minder.core.skill_tools import SkillToolContext, ToolSpec

    specs = mod.register(SkillToolContext())
    assert isinstance(specs, list) and specs
    spec = specs[0]
    assert isinstance(spec, ToolSpec)
    assert spec.name == "enterprise_knowledge_query"
    assert spec.parameters["required"] == ["user_id", "question"]


def test_discovered_via_skill_tool_loader():
    # The module SKILL.md declares `tools: agent_tools.py`; the loader pointed at
    # the modules root must register the tool (this is the registry wiring path).
    from minder.core.skill_tools import SkillToolContext, SkillToolLoader

    specs = SkillToolLoader([REPO / "modules"]).discover_and_register(SkillToolContext())
    names = {s.name for s in specs}
    assert "enterprise_knowledge_query" in names
