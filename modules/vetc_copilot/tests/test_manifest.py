import json
from pathlib import Path


def test_manifest_valid_and_skill_frontmatter():
    root = Path(__file__).resolve().parent.parent
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert m["display_name"] and m["icon"] == "icon.svg"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---")
    assert "name: vetc_copilot" in skill
