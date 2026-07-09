"""BM25 sparse-vector helpers for hybrid retrieval.

Pure and dependency-free: Unicode-aware tokenization plus BM25 document/query
weighting for Qdrant sparse vectors. Document weights carry the BM25 tf
saturation and length normalization; the idf factor is applied by Qdrant's
``Modifier.IDF`` at query time, so query-side values are 1 per term.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

DEFAULT_K1 = 1.5
DEFAULT_B = 0.75

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lowercase, NFC-normalize, and split ``text`` into Unicode word tokens."""
    normalized = unicodedata.normalize("NFC", text).lower()
    return _TOKEN_RE.findall(normalized)


def term_id(token: str) -> int:
    """Return a stable uint32 sparse-index id for ``token`` (hashing trick)."""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def doc_sparse(
    tokens: list[str], avgdl: float, k1: float = DEFAULT_K1, b: float = DEFAULT_B
) -> tuple[list[int], list[float]]:
    """BM25 document-side sparse vector as ``(indices, values)`` over unique terms.

    ``value = tf*(k1+1) / (tf + k1*(1 - b + b*len/avgdl))``; idf is added by Qdrant.
    """
    if not tokens:
        return [], []
    length = len(tokens)
    denom_norm = k1 * (1.0 - b + b * (length / avgdl if avgdl > 0 else 1.0))
    counts: dict[int, int] = {}
    for token in tokens:
        tid = term_id(token)
        counts[tid] = counts.get(tid, 0) + 1
    indices = list(counts.keys())
    values = [tf * (k1 + 1.0) / (tf + denom_norm) for tf in counts.values()]
    return indices, values


def query_sparse(tokens: list[str]) -> tuple[list[int], list[float]]:
    """BM25 query-side sparse vector: ``(indices, values)`` with value 1 per term."""
    indices = sorted({term_id(token) for token in tokens})
    return indices, [1.0] * len(indices)


def average_length(texts: list[str]) -> float:
    """Average token length across ``texts`` (corpus ``avgdl``); 1.0 if empty."""
    lengths = [len(tokenize(t)) for t in texts]
    return sum(lengths) / len(lengths) if lengths else 1.0
