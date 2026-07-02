"""Load a tabular dataset and produce a compact, grounding-friendly profile.

The profile (schema + stats + sample rows) is the context handed to code
generation so the model never guesses column names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd


def load_dataset(path: str) -> pd.DataFrame:
    """Load a CSV / Excel / Parquet file into a DataFrame by extension.

    Args:
        path: Filesystem path to the dataset.

    Returns:
        The loaded :class:`pandas.DataFrame`.

    Raises:
        ValueError: If the extension is unsupported.
        FileNotFoundError: If the path does not exist.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if ext == ".parquet":
        return pd.read_parquet(p)
    raise ValueError(f"unsupported dataset extension: {ext!r}")


def profile_dataframe(df: pd.DataFrame, sample_rows: int = 5) -> Dict[str, Any]:
    """Summarize a DataFrame into a JSON-serializable profile.

    Args:
        df: The DataFrame to profile.
        sample_rows: Number of head rows to include as examples.

    Returns:
        A dict with ``n_rows``, ``n_cols``, ``columns``, ``sample``, and
        ``numeric_summary``.
    """
    columns = [
        {
            "name": str(name),
            "dtype": str(df[name].dtype),
            "non_null": int(df[name].notna().sum()),
            "n_unique": int(df[name].nunique(dropna=True)),
        }
        for name in df.columns
    ]
    numeric = df.select_dtypes(include="number")
    numeric_summary = (
        {} if numeric.empty else {str(k): v for k, v in numeric.describe().to_dict().items()}
    )
    sample = df.head(sample_rows).astype(object).where(pd.notna(df.head(sample_rows)), None)
    return {
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": columns,
        "sample": sample.to_dict(orient="records"),
        "numeric_summary": numeric_summary,
    }


def profile_dataset(path: str, sample_rows: int = 5) -> Dict[str, Any]:
    """Load a dataset and return its profile, tagged with the source path.

    Args:
        path: Filesystem path to the dataset.
        sample_rows: Number of head rows to include as examples.

    Returns:
        The profile dict from :func:`profile_dataframe` plus a ``path`` key.
    """
    df = load_dataset(path)
    prof = profile_dataframe(df, sample_rows=sample_rows)
    prof["path"] = str(path)
    return prof
