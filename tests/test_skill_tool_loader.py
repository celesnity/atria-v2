import logging
from pathlib import Path

from atria.core.skill_tools import (
    SkillToolContext,
    SkillToolLoader,
)


def _write_skill(skill_dir: Path, name: str, tools_py: str, *, declare_tools: bool = True) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    tools_line = "tools: tools.py\n" if declare_tools else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n{tools_line}---\n\nBody.\n",
        encoding="utf-8",
    )
    (skill_dir / "tools.py").write_text(tools_py, encoding="utf-8")


def test_discovers_and_registers(tmp_path: Path):
    _write_skill(
        tmp_path / "alpha",
        "alpha",
        "from atria.core.skill_tools import ToolSpec\n"
        "def register(ctx):\n"
        "    return [ToolSpec(name='alpha_tool', description='d',\n"
        "                    parameters={'type':'object'},\n"
        "                    handler=lambda **k: {'success': True, 'output': 'alpha'})]\n",
    )
    loader = SkillToolLoader([tmp_path])
    specs = loader.discover_and_register(SkillToolContext())
    assert [s.name for s in specs] == ["alpha_tool"]
    assert specs[0].handler()["output"] == "alpha"


def test_skill_without_tools_declaration_ignored(tmp_path: Path):
    _write_skill(
        tmp_path / "beta",
        "beta",
        "def register(ctx):\n    raise AssertionError('should not be called')\n",
        declare_tools=False,
    )
    loader = SkillToolLoader([tmp_path])
    assert loader.discover_and_register(SkillToolContext()) == []


def test_duplicate_tool_name_skips_offending_skill(tmp_path: Path, caplog):
    body = (
        "from atria.core.skill_tools import ToolSpec\n"
        "def register(ctx):\n"
        "    return [ToolSpec(name='dup', description='d',\n"
        "                    parameters={}, handler=lambda **k: {})]\n"
    )
    _write_skill(tmp_path / "one", "one", body)
    _write_skill(tmp_path / "two", "two", body)
    loader = SkillToolLoader([tmp_path])
    with caplog.at_level(logging.WARNING, logger="atria.core.skill_tools"):
        specs = loader.discover_and_register(SkillToolContext())

    # Exactly one of the two colliding skills registers 'dup'; the other is
    # skipped without discarding the one that got there first.
    assert [s.name for s in specs] == ["dup"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "Duplicate tool name 'dup'" in message
    # The offending skill's SKILL.md and its colliding tools.py are both named.
    assert "SKILL.md" in message
    assert "tools.py" in message


def test_missing_register_skips_and_logs_warning(tmp_path: Path, caplog):
    _write_skill(tmp_path / "no_reg", "no_reg", "# no register\n")
    _write_skill(
        tmp_path / "good",
        "good",
        "from atria.core.skill_tools import ToolSpec\n"
        "def register(ctx):\n"
        "    return [ToolSpec(name='good_tool', description='d',\n"
        "                    parameters={}, handler=lambda **k: {'output': 'good'})]\n",
    )
    loader = SkillToolLoader([tmp_path])
    with caplog.at_level(logging.WARNING, logger="atria.core.skill_tools"):
        specs = loader.discover_and_register(SkillToolContext())

    assert [s.name for s in specs] == ["good_tool"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "missing required `register" in message
    assert str((tmp_path / "no_reg" / "tools.py").resolve()) in message


def test_register_non_list_return_skips_and_logs_warning(tmp_path: Path, caplog):
    _write_skill(
        tmp_path / "bad",
        "bad",
        "def register(ctx):\n    return 'not a list'\n",
    )
    _write_skill(
        tmp_path / "good",
        "good",
        "from atria.core.skill_tools import ToolSpec\n"
        "def register(ctx):\n"
        "    return [ToolSpec(name='good_tool', description='d',\n"
        "                    parameters={}, handler=lambda **k: {'output': 'good'})]\n",
    )
    loader = SkillToolLoader([tmp_path])
    with caplog.at_level(logging.WARNING, logger="atria.core.skill_tools"):
        specs = loader.discover_and_register(SkillToolContext())

    assert [s.name for s in specs] == ["good_tool"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "must return list" in message
    assert str((tmp_path / "bad" / "tools.py").resolve()) in message


def test_skill_can_use_sibling_module(tmp_path: Path):
    """Sibling modules in the skill folder should resolve via relative import."""
    skill = tmp_path / "with_sibling"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: with_sibling\ndescription: d\ntools: tools.py\n---\n",
        encoding="utf-8",
    )
    (skill / "helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    (skill / "tools.py").write_text(
        "from atria.core.skill_tools import ToolSpec\n"
        "from .helper import VALUE\n"
        "def register(ctx):\n"
        "    return [ToolSpec(name='sib', description='d', parameters={},\n"
        "                    handler=lambda **k: {'value': VALUE})]\n",
        encoding="utf-8",
    )
    loader = SkillToolLoader([tmp_path])
    specs = loader.discover_and_register(SkillToolContext())
    assert specs[0].handler()["value"] == 42
