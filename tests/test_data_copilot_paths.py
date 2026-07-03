"""Tests for the session-keyed data_copilot artifact path resolution."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "dc_paths",
    Path(__file__).resolve().parent.parent
    / "modules" / "data_copilot" / "scripts" / "paths.py",
)
paths = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(paths)  # type: ignore[union-attr]


def test_session_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ATRIA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ATRIA_CONVERSATION_ID", "abcd1234")
    monkeypatch.delenv("ATRIA_SESSION_DIR", raising=False)
    root = paths.conversation_root()
    assert root == tmp_path / ".artifacts" / "data_copilot" / "abcd1234"
    assert paths.data_dir() == root / "data"
    assert paths.runs_dir() == root / "runs"
    assert paths.audit_path() == root / "audit.jsonl"
    assert paths.data_dir().is_dir()
    run = paths.new_run_dir()
    assert run == root / "runs" / "latest" and run.is_dir()


def test_fallback_to_module_dir_when_env_missing(monkeypatch):
    monkeypatch.delenv("ATRIA_WORKSPACE", raising=False)
    monkeypatch.delenv("ATRIA_SESSION_DIR", raising=False)
    monkeypatch.delenv("ATRIA_CONVERSATION_ID", raising=False)
    module_dir = Path(paths.__file__).resolve().parent.parent
    assert paths.conversation_root() == module_dir
    assert paths.data_dir() == module_dir / "data"
    assert paths.audit_path() == module_dir / "audit_log.jsonl"
