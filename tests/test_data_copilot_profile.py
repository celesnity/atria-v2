"""Tests for dataset loading + profiling."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _demo_csv() -> str:
    return str(_MOD.parent / "sample_data" / "demo.csv")


def test_profile_csv_shape_and_columns():
    profile = _load("profile", "dc_profile_csv")
    prof = profile.profile_dataset(_demo_csv())
    assert prof["n_rows"] == 8
    assert prof["n_cols"] == 5
    names = [c["name"] for c in prof["columns"]]
    assert names == ["region", "product", "units", "revenue", "date"]
    assert len(prof["sample"]) == 5
    # numeric columns appear in the numeric summary
    assert "revenue" in prof["numeric_summary"]


def test_load_dataset_unsupported_extension_raises(tmp_path):
    profile = _load("profile", "dc_profile_bad")
    bad = tmp_path / "data.txt"
    bad.write_text("not a table")
    with pytest.raises(ValueError):
        profile.load_dataset(str(bad))


def test_numeric_summary_is_strict_json_serializable():
    import json
    import pandas as pd
    profile = _load("profile", "dc_profile_nan")
    df = pd.DataFrame({"empty": pd.Series([None, None], dtype="float64"),
                       "one": pd.Series([5.0, None])})
    prof = profile.profile_dataframe(df)
    dumped = json.dumps(prof, allow_nan=False)
    assert "NaN" not in dumped
    assert prof["numeric_summary"]["empty"]["mean"] is None
