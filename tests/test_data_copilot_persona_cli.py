"""Tests the `persona` subcommand parses and dispatches to run_persona."""

import importlib.util
import json
import sys
from pathlib import Path


def _load_copilot():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_copilot", base / "copilot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_parser_has_persona_subcommand():
    cop = _load_copilot()
    args = cop.build_parser().parse_args(
        ["persona", "data.csv", "segment customers", "--domain", "telecom", "--k", "4"]
    )
    assert args.command == "persona"
    assert args.dataset == "data.csv"
    assert args.question == "segment customers"
    assert args.domain == "telecom"
    assert args.k == 4


def test_persona_requires_question(capsys):
    cop = _load_copilot()
    rc = cop._cmd_persona("data.csv", None, "out", 0, 0, None, None)
    assert rc == 1
    assert "question is required" in json.loads(capsys.readouterr().out)["error"]
