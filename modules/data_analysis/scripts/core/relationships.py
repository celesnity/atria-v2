"""Cross-dataset relationship discovery (FR-DATA-04).

Heuristic + confidence scoring without a learning model:

  * name similarity (token overlap on column names)
  * type compatibility (numeric ↔ numeric, string ↔ string)
  * cardinality overlap on a sample (value-set intersection on the
    smaller side)

Score ∈ [0, 1]. The PRD policy:
  ≥ 0.75 → auto-join
  0.4 .. 0.75 → suggest, require user confirmation
  < 0.4 → drop
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .duck import connect


def _name_sim(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.7
    at = set(a.replace("-", "_").split("_"))
    bt = set(b.replace("-", "_").split("_"))
    if not at or not bt:
        return 0.0
    inter = at & bt
    return len(inter) / max(len(at | bt), 1)


def _type_compat(t1: str, t2: str) -> float:
    n = ("INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "SMALLINT", "TINYINT")
    a_num = any(k in t1.upper() for k in n)
    b_num = any(k in t2.upper() for k in n)
    if a_num and b_num:
        return 1.0
    if not a_num and not b_num:
        return 0.8
    return 0.1


def _value_overlap(p1: Path, c1: str, p2: Path, c2: str, sample: int = 2000) -> float:
    con = connect()
    try:
        s_p1 = str(p1).replace("'", "''")
        s_p2 = str(p2).replace("'", "''")
        con.execute(f"CREATE VIEW a AS SELECT * FROM read_parquet('{s_p1}')")
        con.execute(f"CREATE VIEW b AS SELECT * FROM read_parquet('{s_p2}')")
        s1 = {row[0] for row in con.execute(f'SELECT DISTINCT "{c1}" FROM a WHERE "{c1}" IS NOT NULL LIMIT {sample}').fetchall()}
        s2 = {row[0] for row in con.execute(f'SELECT DISTINCT "{c2}" FROM b WHERE "{c2}" IS NOT NULL LIMIT {sample}').fetchall()}
    except Exception:
        return 0.0
    finally:
        con.close()
    if not s1 or not s2:
        return 0.0
    inter = s1 & s2
    return len(inter) / min(len(s1), len(s2))


def discover(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairwise candidate join keys with confidence."""
    candidates: list[dict[str, Any]] = []
    for i, d1 in enumerate(datasets):
        for d2 in datasets[i + 1:]:
            p1 = Path(d1["parquet"])
            p2 = Path(d2["parquet"])
            for c1 in d1.get("columns", []):
                for c2 in d2.get("columns", []):
                    name = _name_sim(c1["name"], c2["name"])
                    if name < 0.5:
                        continue
                    types = _type_compat(c1.get("type", ""), c2.get("type", ""))
                    if types < 0.5:
                        continue
                    overlap = _value_overlap(p1, c1["name"], p2, c2["name"])
                    score = 0.4 * name + 0.2 * types + 0.4 * overlap
                    if score < 0.4:
                        continue
                    decision = "auto" if score >= 0.75 else "suggest"
                    candidates.append({
                        "left": {"dataset_id": d1["id"], "name": d1["name"], "column": c1["name"]},
                        "right": {"dataset_id": d2["id"], "name": d2["name"], "column": c2["name"]},
                        "score": round(score, 3),
                        "name_sim": round(name, 3),
                        "type_compat": round(types, 3),
                        "value_overlap": round(overlap, 3),
                        "decision": decision,
                    })
    candidates.sort(key=lambda c: -c["score"])
    return candidates
