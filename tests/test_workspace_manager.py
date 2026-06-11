# tests/test_workspace_manager.py
from pathlib import Path
from atria.core.workspace.manager import (
    slugify,
    workspace_base,
    project_path,
    conversation_path,
    is_within_workspace,
)


def test_slugify_basic():
    assert slugify("My Cool Project") == "my-cool-project"


def test_slugify_special_chars():
    assert slugify("Đề tài nghiên cứu!") == "e-tai-nghien-cuu"


def test_slugify_strips_multiple_hyphens():
    assert slugify("a  --  b") == "a-b"


def test_slugify_empty():
    assert slugify("") == "untitled"


def test_slugify_max_length():
    assert len(slugify("a" * 100)) <= 50


def test_workspace_base_is_under_home():
    base = workspace_base()
    assert str(base).startswith(str(Path.home()))


def test_project_path_structure():
    p = project_path("alice", "My Project")
    assert p == workspace_base() / "alice" / "my-project"


def test_conversation_path_under_project():
    proj = project_path("alice", "My Project")
    c = conversation_path(proj, "Chat 1")
    assert c == proj / "chat-1"


def test_is_within_workspace_true(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    inner = workspace / "file.txt"
    assert is_within_workspace(inner, workspace) is True


def test_is_within_workspace_false(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "other" / "file.txt"
    assert is_within_workspace(outside, workspace) is False


def test_is_within_workspace_traversal(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    traversal = workspace / ".." / "other"
    assert is_within_workspace(traversal, workspace) is False
