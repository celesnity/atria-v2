"""Pure-Python TF-IDF cosine retriever over small text tables (no external index)."""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(str(text).lower())


class Retriever:
    """Rank rows by TF-IDF cosine similarity of their concatenated text fields."""

    def __init__(self, rows: list[dict], text_fields: tuple[str, ...] =
                 ("question", "answer", "topic"), id_field: str = "knowledge_id") -> None:
        self._rows = rows
        self._id_field = id_field
        self._docs = [_tokens(" ".join(str(r.get(f, "")) for f in text_fields)) for r in rows]
        df: Counter = Counter()
        for toks in self._docs:
            df.update(set(toks))
        n = max(1, len(self._docs))
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self._vecs = [self._vectorize(toks) for toks in self._docs]

    def _vectorize(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        return {t: (c / len(toks)) * self._idf.get(t, 0.0) for t, c in tf.items()} if toks else {}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(a[t] * b.get(t, 0.0) for t in a)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query: str, k: int = 3) -> list[dict]:
        """Return the top-k rows (with ``_score``) whose similarity to ``query`` is > 0."""
        qvec = self._vectorize(_tokens(query))
        scored = []
        for row, vec in zip(self._rows, self._vecs):
            s = self._cosine(qvec, vec)
            if s > 0:
                scored.append({**row, "_score": round(s, 6)})
        scored.sort(key=lambda r: r["_score"], reverse=True)
        return scored[:k]
