"""Bring a dataset into the data_copilot module's ``data/`` dir.

Copies/converts a source file (CSV, Excel, Parquet) into
``modules/data_copilot/data/<name>.csv`` via Atria's module store. This makes the
dataset addressable by two core features:

- the ``send_editable_table`` tool, which renders and writes back CSVs that live
  under a module's ``data/`` dir (so the user can review/fix the source data
  inline before analysis); and
- the analyze/profile loop, which reads the absolute copy.

CSV files are copied byte-for-byte. Excel workbooks are converted to one CSV per
sheet via the shared ``xlsx_convert`` helper (multi-sheet books yield
``<name>__<sheet>.csv``). Parquet and legacy ``.xls`` are loaded with pandas and
written out as CSV.

The heavy imports (``atria.core.modules`` and ``pandas``) are deferred into the
functions so importing this module stays cheap.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import List, Optional, Tuple

MODULE_NAME = "data_copilot"


def _module_root() -> Path:
    """Return the modules root to write into.

    Prefers Atria's own resolver (``resolve_modules_root`` — honors
    ``ATRIA_MODULES_DIR``/CWD) so ingest writes to the exact directory the
    ``send_editable_table`` tool later reads from. Falls back to this script's
    physical location (``modules/data_copilot/scripts/ingest.py`` → three parents
    up) if the resolver is unavailable.
    """
    try:
        from atria.core.modules.registry import resolve_modules_root

        return resolve_modules_root()
    except Exception:  # noqa: BLE001 — fall back to the script-relative modules dir
        return Path(__file__).resolve().parent.parent.parent


def _slug(text: str) -> str:
    """Filesystem-safe lowercase base name for a stored dataset."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "dataset"


def to_csv_files(src: Path, base_name: str) -> List[Tuple[str, bytes]]:
    """Convert *src* into one or more ``(filename, csv_bytes)`` pairs.

    Raises:
        ValueError: if the file extension is not a supported tabular format.
    """
    ext = src.suffix.lower()
    if ext == ".csv":
        return [(f"{base_name}.csv", src.read_bytes())]
    if ext in (".xlsx", ".xlsm"):
        # Shared core helper — one CSV per non-empty worksheet.
        from atria.core.modules.xlsx_convert import xlsx_to_csvs

        return xlsx_to_csvs(src.read_bytes(), base_name)
    if ext in (".xls", ".parquet"):
        import pandas as pd

        df = pd.read_parquet(src) if ext == ".parquet" else pd.read_excel(src)
        buf = io.StringIO(newline="")
        df.to_csv(buf, index=False)
        return [(f"{base_name}.csv", buf.getvalue().encode("utf-8"))]
    raise ValueError(f"unsupported file type: {ext!r} (use .csv, .xlsx, .xls, .parquet)")


def ingest(
    source: str,
    name: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    module_name: str = MODULE_NAME,
) -> dict:
    """Copy/convert *source* into the module's ``data/`` dir.

    Args:
        source: Path to a CSV/Excel/Parquet file.
        name: Base name for the stored CSV(s); defaults to the source stem.
        root: Modules root (defaults to the real modules dir; overridable in tests).
        module_name: Target module (defaults to ``data_copilot``).

    Returns:
        ``{"module", "files": [{"file", "path"}, ...]}`` where ``file`` is the
        ``data/``-relative path to pass to ``send_editable_table`` and ``path`` is
        the absolute path to pass to ``analyze``/``profile``.

    Raises:
        FileNotFoundError: if *source* does not exist.
        ValueError: on unsupported file types or store validation failures.
    """
    from atria.core.modules import store

    src = Path(source).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"source not found: {source}")

    base = _slug(name or src.stem)
    pairs = to_csv_files(src, base)

    modules_root = root or _module_root()
    written = store.write_data_files(modules_root, module_name, pairs)  # ["data/x.csv", ...]

    module_dir = modules_root / module_name
    files = []
    for rel in written:
        data_rel = rel[len("data/") :] if rel.startswith("data/") else rel
        files.append({"file": data_rel, "path": str(module_dir / rel)})
    return {"module": module_name, "files": files}


def list_datasets(*, root: Optional[Path] = None, module_name: str = MODULE_NAME) -> List[dict]:
    """List CSV datasets under the module's ``data/`` dir.

    Returns one entry per ``*.csv`` (``.bak`` files excluded) with its
    ``data/``-relative ``file`` (for ``send_editable_table``/``analyze``), the
    absolute ``path``, byte ``size``, and header ``columns``. Powers the
    dashboard's dataset picker. Returns ``[]`` when no data dir exists yet.
    """
    modules_root = root or _module_root()
    data_dir = modules_root / module_name / "data"
    if not data_dir.is_dir():
        return []

    out: List[dict] = []
    for p in sorted(data_dir.glob("*.csv")):
        columns: List[str] = []
        try:
            with p.open("r", encoding="utf-8", errors="replace", newline="") as fh:
                first_line = fh.readline()
            columns = next(csv.reader([first_line]), [])
        except OSError:
            pass
        out.append(
            {
                "file": p.name,
                "path": str(p),
                "size": p.stat().st_size,
                "columns": columns,
            }
        )
    return out
