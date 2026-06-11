"""CSV/XLSX -> SQLite loader + schema profiler for deep_analyze."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .validation import AnalyzeValidationError

_MAX_ROWS = 100_000


def _read_dataframe(p: Path) -> pd.DataFrame:
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    return pd.read_excel(p)


def load_to_sqlite(file_path: Path, db_path: Path) -> int:
    df = _read_dataframe(file_path)
    if len(df) > _MAX_ROWS:
        raise AnalyzeValidationError(f"File has {len(df)} rows, exceeds {_MAX_ROWS} limit.")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as cx:
        df.to_sql("raw", cx, index=False, if_exists="replace")
    return len(df)


def _dtype_label(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_integer_dtype(s):
        return "int"
    if pd.api.types.is_float_dtype(s):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    return "string"


def profile_schema(db_path: Path, file_name: str) -> Dict[str, Any]:
    with sqlite3.connect(db_path) as cx:
        df = pd.read_sql_query("SELECT * FROM raw", cx)
    columns: List[Dict[str, Any]] = []
    for name in df.columns:
        s = df[name]
        col: Dict[str, Any] = {
            "name": str(name),
            "dtype": _dtype_label(s),
            "null_pct": float(s.isna().mean()),
            "sample": [str(v) for v in s.dropna().head(3).tolist()],
        }
        if col["dtype"] in {"int", "float"}:
            col["min"] = float(s.min()) if len(s) else None
            col["max"] = float(s.max()) if len(s) else None
            col["mean"] = float(s.mean()) if len(s) else None
        elif col["dtype"] == "string":
            col["n_unique"] = int(s.nunique())
        columns.append(col)
    return {"file_name": file_name, "row_count": int(len(df)), "columns": columns}
