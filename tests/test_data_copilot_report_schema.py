import importlib.util, sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[sentinel] = mod
    spec.loader.exec_module(mod); return mod


def test_report_narrative_shape():
    rs = _load("report_schema", "dc_report_schema")
    n = rs.ReportNarrative(
        executive_summary=rs.ExecutiveSummaryNarrative(executive_overview="ov"),
        personas_analysis=[rs.PersonaNarrative(cluster_id=0, business_interpretation="bi", operational_impact="oi")],
        recommendations_analysis=[rs.ActionNarrative(cluster_id=0, expected_outcome="eo")],
        conclusion="c",
    )
    assert n.executive_summary.executive_overview == "ov"
    assert n.personas_analysis[0].cluster_id == 0
