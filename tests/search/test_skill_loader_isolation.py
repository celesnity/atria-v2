"""Tests for per-skill fault isolation in SkillToolLoader.discover_and_register.

Reproduces the production failure: modules/maintenance_copilot/SKILL.md declares
`tools: tools.py` but the file is runtime-vendored and absent on dev machines,
which previously raised SkillToolError out of the whole discovery pass and
degraded ToolRegistry to zero skill tools (see ToolRegistry.__init__). These
tests assert that a broken skill is skipped in isolation while healthy skills
(e.g. knowledge_search) still register.
"""

from pathlib import Path

from minder.core.skill_tools import SkillToolContext, SkillToolLoader, ToolSpec


def _write_good_skill(root: Path) -> None:
    """Write a skill with a working tools.py that registers one ToolSpec."""
    skill_dir = root / "good_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: good_skill\ndescription: test\ntools: tools.py\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (skill_dir / "tools.py").write_text(
        "from minder.core.skill_tools import ToolSpec\n"
        "def register(ctx):\n"
        "    return [ToolSpec(name='good_tool', description='d',\n"
        "                    parameters={'type': 'object'},\n"
        "                    handler=lambda **k: {'success': True, 'output': 'good'})]\n",
        encoding="utf-8",
    )


def _write_broken_skill_missing_tools_file(root: Path) -> None:
    """Write a skill that declares a tools.py which does not exist on disk.

    This is the exact production failure: modules/maintenance_copilot/SKILL.md
    declares `tools: tools.py`, but the file is absent (runtime-vendored).
    """
    skill_dir = root / "broken_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: broken_skill\ndescription: test\ntools: tools.py\n---\n\nBody.\n",
        encoding="utf-8",
    )
    # Deliberately no tools.py written.


def _write_broken_skill_import_error(root: Path) -> None:
    """Write a skill whose tools.py raises at import time."""
    skill_dir = root / "broken_import_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: broken_import_skill\ndescription: test\ntools: tools.py\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (skill_dir / "tools.py").write_text(
        "raise RuntimeError('boom at import time')\n",
        encoding="utf-8",
    )


def test_missing_tools_file_is_isolated_from_good_skill(tmp_path: Path):
    """A skill declaring a missing tools.py must not prevent other skills' tools.

    This is the exact production bug: maintenance_copilot's declared tools.py is
    absent on dev machines, and previously that killed discovery for every other
    skill (e.g. knowledge_search).
    """
    _write_good_skill(tmp_path)
    _write_broken_skill_missing_tools_file(tmp_path)

    loader = SkillToolLoader([tmp_path])
    specs = loader.discover_and_register(SkillToolContext())

    assert len(specs) == 1
    assert isinstance(specs[0], ToolSpec)
    assert specs[0].name == "good_tool"
    assert specs[0].handler()["output"] == "good"


def test_import_time_error_is_isolated_from_good_skill(tmp_path: Path):
    """A skill whose tools.py raises at import time must not sink other skills."""
    _write_good_skill(tmp_path)
    _write_broken_skill_import_error(tmp_path)

    loader = SkillToolLoader([tmp_path])
    specs = loader.discover_and_register(SkillToolContext())

    assert len(specs) == 1
    assert specs[0].name == "good_tool"
