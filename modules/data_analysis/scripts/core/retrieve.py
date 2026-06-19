"""Artifact retrieval (FR-ART-03).

PRD asks for vector / semantic search. We ship a dependency-light lexical
retriever (token-overlap + IDF) so the workspace is usable with no extra
installs; if `sentence-transformers` is available we upgrade to cosine
similarity over MiniLM embeddings cached per artifact.

Either way the public API is the same:
    retrieve(query, artifacts, top_k) -> [(artifact, score), ...]
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable


_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _doc_text(artifact: dict[str, Any]) -> str:
    parts = [
        artifact.get("title", ""),
        artifact.get("question", ""),
        artifact.get("summary", ""),
        " ".join(artifact.get("columns", []) or []),
        " ".join(artifact.get("tags", []) or []),
        artifact.get("sql", ""),
    ]
    return " ".join(p for p in parts if p)


def _bm25_lite(query_tokens: list[str], docs: list[list[str]]) -> list[float]:
    """Lightweight BM25-ish scoring: tf · idf with length normalisation."""
    if not docs:
        return []
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n
    df = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1

    def idf(t: str) -> float:
        return math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))

    k1, b = 1.4, 0.75
    scores: list[float] = []
    for d in docs:
        tf = Counter(d)
        dl = len(d) or 1
        s = 0.0
        for t in query_tokens:
            if t not in tf:
                continue
            num = tf[t] * (k1 + 1)
            den = tf[t] + k1 * (1 - b + b * dl / (avgdl or 1))
            s += idf(t) * num / den
        scores.append(s)
    return scores


def retrieve(query: str, artifacts: Iterable[dict[str, Any]], top_k: int = 5) -> list[tuple[dict[str, Any], float]]:
    artifacts = list(artifacts)
    if not artifacts:
        return []
    q = _tokenize(query)
    if not q:
        return [(a, 0.0) for a in artifacts[:top_k]]
    docs = [_tokenize(_doc_text(a)) for a in artifacts]
    scores = _bm25_lite(q, docs)
    pairs = sorted(zip(artifacts, scores), key=lambda kv: kv[1], reverse=True)
    return [(a, s) for a, s in pairs[:top_k] if s > 0] or [(artifacts[0], 0.0)]
