"""Tests for run_persona: artifact writing, verify loop, summary shape."""

import importlib.util
import json
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona", base / "persona.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_PERSONAS = [
    {
        "cluster_id": 0,
        "persona_name": "x",
        "support": 10,
        "support_pct": 0.5,
        "confidence": "HIGH",
        "priority_score": 0.5,
        "is_anomaly": False,
        "segmentation_quality": "NORMAL",
        "risk_tier": "LOW",
        "evidence": {"a": 1.0},
        "profile_attributes": {},
        "recommended_actions": ["do x"],
        "sample_persona_text": "t",
    }
]


def _stdout():
    return "[JSON_START_PERSONA]\n" + json.dumps(_PERSONAS) + "\n[JSON_END_PERSONA]"


def test_run_persona_writes_persona_json_and_summary(tmp_path):
    mod = _load()
    out = tmp_path / "run"
    out.mkdir()

    def fake_exec(code, out_dir, timeout, max_output):
        (Path(out_dir) / "result.csv").write_text(
            "persona_name,support\nx,10\n", encoding="utf-8"
        )
        return {
            "status": "ok",
            "stdout": _stdout(),
            "stderr": "",
            "figures": [],
            "returncode": 0,
        }

    summary = mod.run_persona(
        dataset=str(tmp_path / "in.csv"),
        question="segment",
        out_dir=str(out),
        max_repair=0,
        max_verify=0,
        codegen_fn=lambda q, p, pe=None, hy=None: "print('x')",
        verify_fn=lambda q, c, o, personas: {"status": "OK", "hypotheses": "", "warnings": []},
        report_fn=lambda personas, q, verified=True: "# report",
        profile_fn=lambda ds: {"path": ds, "columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    persona_json = out / "persona.json"
    assert persona_json.is_file()
    assert json.loads(persona_json.read_text())[0]["persona_name"] == "x"
    assert summary["persona_json"] == str(persona_json.resolve())
    # personas pass through persona_sanitize: core fields preserved, and
    # risk/risk_tier are re-derived from priority_score (0.5 -> LOW bucket).
    persona = summary["personas"][0]
    assert persona["persona_name"] == "x"
    assert persona["evidence"] == {"a": 1.0}
    assert persona["risk"] == "LOW"
    assert persona["risk_tier"] == "Nhóm ổn định – theo dõi định kỳ"
    assert summary["verified"] is True
    assert summary["result_table"] == str((out / "result.csv").resolve())
    assert summary["suggestions"]  # bar chart from persona_name/support


def test_run_persona_unverified_when_block_missing(tmp_path):
    mod = _load()
    out = tmp_path / "run2"
    out.mkdir()

    def fake_exec(code, out_dir, timeout, max_output):
        return {
            "status": "ok",
            "stdout": "no personas",
            "stderr": "",
            "figures": [],
            "returncode": 0,
        }

    summary = mod.run_persona(
        dataset=str(tmp_path / "in.csv"),
        question="segment",
        out_dir=str(out),
        max_repair=0,
        max_verify=1,
        codegen_fn=lambda q, p, pe=None, hy=None: "print('x')",
        verify_fn=lambda q, c, o, personas: {
            "status": "REVISE",
            "hypotheses": "no block",
            "warnings": [],
        },
        report_fn=lambda personas, q, verified=True: "# report",
        profile_fn=lambda ds: {"path": ds, "columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    assert summary["verified"] is False
    assert summary["personas"] == []
    assert summary["persona_json"] is None
