from __future__ import annotations

from pathlib import Path

import pytest

from atria.core.modules import store
from atria.core.modules.registry import ModuleRegistry, load_disabled_modules


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "modules"


def test_load_all_populates_from_disk(root: Path):
    store.create_module(root, "alpha")
    store.create_module(root, "beta")
    reg = ModuleRegistry(root)
    reg.load_all()
    assert sorted(reg.names()) == ["alpha", "beta"]
    assert reg.version == 1


def test_reload_one_updates_in_place_and_bumps_version(root: Path):
    store.create_module(root, "alpha")
    reg = ModuleRegistry(root)
    reg.load_all()
    v0 = reg.version
    store.write_file(root, "alpha", "SKILL.md", "# changed")
    reg.reload_one("alpha")
    assert reg.get("alpha").skill_md == "# changed"
    assert reg.version == v0 + 1


def test_reload_one_for_deleted_module_removes_it(root: Path):
    store.create_module(root, "alpha")
    reg = ModuleRegistry(root)
    reg.load_all()
    store.delete_module(root, "alpha")
    reg.reload_one("alpha")
    assert "alpha" not in reg.names()


def test_remove_explicit(root: Path):
    store.create_module(root, "alpha")
    reg = ModuleRegistry(root)
    reg.load_all()
    v = reg.version
    reg.remove("alpha")
    assert "alpha" not in reg.names()
    assert reg.version == v + 1


def test_all_returns_sorted_list(root: Path):
    store.create_module(root, "bravo")
    store.create_module(root, "alpha")
    reg = ModuleRegistry(root)
    reg.load_all()
    assert [m.name for m in reg.all()] == ["alpha", "bravo"]


def test_load_disabled_modules_parses_env(monkeypatch):
    monkeypatch.setenv("ATRIA_DISABLED_MODULES", "alpha, beta  gamma")
    assert load_disabled_modules() == {"alpha", "beta", "gamma"}
    monkeypatch.setenv("ATRIA_DISABLED_MODULES", "")
    assert load_disabled_modules() == set()
    monkeypatch.delenv("ATRIA_DISABLED_MODULES", raising=False)
    assert load_disabled_modules() == set()


def test_load_all_skips_disabled_modules(root: Path, monkeypatch):
    store.create_module(root, "alpha")
    store.create_module(root, "beta")
    monkeypatch.setenv("ATRIA_DISABLED_MODULES", "beta")
    reg = ModuleRegistry(root)
    reg.load_all()
    assert reg.names() == ["alpha"]


def test_load_all_disables_everything_with_wildcard(root: Path, monkeypatch):
    store.create_module(root, "alpha")
    store.create_module(root, "beta")
    for value in ("*", "all"):
        monkeypatch.setenv("ATRIA_DISABLED_MODULES", value)
        reg = ModuleRegistry(root)
        reg.load_all()
        assert reg.names() == []


def test_reload_one_ignores_disabled_module(root: Path, monkeypatch):
    store.create_module(root, "alpha")
    reg = ModuleRegistry(root)
    reg.load_all()
    monkeypatch.setenv("ATRIA_DISABLED_MODULES", "alpha")
    reg.reload_one("alpha")
    assert "alpha" not in reg.names()
