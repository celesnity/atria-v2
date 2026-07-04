"""Regression: tool-result message content must always be a string.

get_subagent_output returns its `output` as a dict.
Before the fix that dict flowed unchanged into a message's `content`, and the
compaction token counter crashed with `TypeError: expected string or buffer`
when it later called tiktoken's encode() on the dict.

The coercion lives in ``atria/repl/react_executor/_content.py::as_text`` (a
dependency-light helper so it is testable without importing the whole react
executor stack, which needs optional deps unavailable in every env). This test
exercises that helper and confirms tiktoken can encode its output.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_as_text():
    base = Path(__file__).resolve().parent.parent / "atria" / "repl" / "react_executor"
    spec = importlib.util.spec_from_file_location("dc_rx_content", base / "_content.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.as_text


def test_dict_is_stringified():
    as_text = _load_as_text()
    out = as_text({"status": "completed", "winner": "candidate-2"})
    assert isinstance(out, str)
    assert "completed" in out and "candidate-2" in out


def test_string_is_preserved():
    as_text = _load_as_text()
    assert as_text("plain string answer") == "plain string answer"


def test_list_is_stringified():
    as_text = _load_as_text()
    out = as_text([{"a": 1}, {"b": 2}])
    assert isinstance(out, str) and '"a"' in out


def test_none_becomes_empty_string():
    as_text = _load_as_text()
    assert as_text(None) == ""


def test_non_json_serializable_falls_back_to_str():
    as_text = _load_as_text()
    out = as_text(object())
    assert isinstance(out, str) and out  # non-empty, did not raise


def test_output_is_encodable_by_token_counter():
    """The stringified content must not crash the tiktoken-based counter."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from atria.core.context_engineering.retrieval.token_monitor import ContextTokenMonitor
    except (ImportError, SyntaxError) as exc:
        # The token_monitor import chain needs deps/Python version not present in
        # every dev env (e.g. typing.NotRequired requires 3.11+, prod runs 3.12).
        pytest.skip(f"token_monitor unimportable in this env: {exc}")

    as_text = _load_as_text()
    content = as_text({"status": "completed", "n": 3})
    tm = ContextTokenMonitor()
    assert tm.count_tokens(content) > 0  # must not raise TypeError
    # Defense-in-depth: the counter itself tolerates a raw non-string.
    assert tm.count_tokens({"status": "completed"}) > 0
    assert tm.count_tokens(None) == 0
