#!/usr/bin/env python
"""Local, zero-dependency RAG retriever for the ``rag`` module.

Indexes text from a folder and/or explicit files into a TF-IDF vector store
(``data/index.json``), then answers ``query`` requests by ranked cosine
similarity. No API calls, no external packages — pure Python so it runs
offline and reproducibly.

Commands
--------
    index <path> [<path> ...]   Index a directory (crawled) and/or files.
    query "<text>" [--k N]      Retrieve the top-N chunks for a question.
    list                        Show what is currently indexed.
    reset                       Delete the index.

The index directory defaults to ``<modules>/rag/data`` and can be overridden
with ``ATRIA_RAG_DIR``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Text file extensions we read directly. Anything not here (and not a PDF) is
# skipped with a warning.
TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".rst", ".text",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml",
    ".html", ".css", ".sh", ".cfg", ".ini", ".csv", ".log",
}

# PDFs are extracted to text via a best-effort chain of backends (see
# ``_read_pdf``): poppler's ``pdftotext`` CLI, then ``pypdf``, then PyMuPDF.
PDF_EXTS = {".pdf"}

# Everything we know how to turn into text.
DOC_EXTS = TEXT_EXTS | PDF_EXTS

# Chunking: ~1000 chars per chunk with 150 char overlap, split on blank lines
# first so paragraphs stay intact where possible.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Tiny English stopword set — enough to stop the ranking being dominated by
# filler without shipping a full NLP dependency.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "these",
    "those", "with", "as", "at", "by", "from", "into", "up", "out", "so", "no",
    "not", "do", "does", "did", "can", "will", "would", "should", "could",
}


def _data_dir() -> Path:
    env = os.environ.get("ATRIA_RAG_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "data").resolve()


def _index_path() -> Path:
    return _data_dir() / "index.json"


# ── Text processing ────────────────────────────────────────────────────────


def tokenize(text: str) -> List[str]:
    """Lowercase, split on word chars, drop stopwords and 1-char tokens."""
    return [
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in _STOPWORDS
    ]


def chunk_text(text: str) -> List[str]:
    """Split ``text`` into overlapping chunks, preferring paragraph breaks."""
    text = text.strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for para in paras:
        if not buf:
            buf = para
        elif len(buf) + len(para) + 2 <= CHUNK_SIZE:
            buf = f"{buf}\n\n{para}"
        else:
            chunks.append(buf)
            # Carry a tail of the previous chunk for context overlap.
            tail = buf[-CHUNK_OVERLAP:]
            buf = f"{tail}\n\n{para}" if len(para) < CHUNK_SIZE else para
        # A single oversized paragraph gets hard-split.
        while len(buf) > CHUNK_SIZE:
            chunks.append(buf[:CHUNK_SIZE])
            buf = buf[CHUNK_SIZE - CHUNK_OVERLAP:]
    if buf.strip():
        chunks.append(buf)
    return chunks


# ── Corpus discovery ───────────────────────────────────────────────────────


def _iter_files(paths: Iterable[str]) -> List[Path]:
    """Expand ``paths`` (dirs crawled recursively, files taken as-is)."""
    out: List[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in DOC_EXTS:
                    out.append(child)
        elif p.is_file():
            out.append(p)
        else:
            print(f"warn: path not found, skipping: {p}", file=sys.stderr)
    return out


def _read_pdf(path: Path) -> str | None:
    """Extract text from a PDF via the first backend that works.

    Order: poppler ``pdftotext`` (fast, high quality) → ``pypdf`` → PyMuPDF
    (``fitz``). Returns ``None`` (with a warning) if none is available or the
    PDF has no extractable text layer (e.g. a scanned image with no OCR).
    """
    exe = shutil.which("pdftotext")
    if exe:
        try:
            res = subprocess.run(
                [exe, "-q", "-enc", "UTF-8", str(path), "-"],
                capture_output=True, text=True, timeout=120,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if text.strip():
            return text
    except Exception:  # noqa: BLE001 — any parser error → try the next backend
        pass

    try:
        import fitz  # type: ignore  # PyMuPDF

        with fitz.open(str(path)) as doc:
            text = "\n\n".join(page.get_text() for page in doc)
        if text.strip():
            return text
    except Exception:  # noqa: BLE001
        pass

    print(
        f"warn: no PDF text extracted (install poppler or pypdf, or the file "
        f"may be a scanned image): {path}",
        file=sys.stderr,
    )
    return None


def _read_source(path: Path) -> str | None:
    """Read a file to text: PDFs via ``_read_pdf``, known text types directly."""
    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        return _read_pdf(path)
    if ext not in TEXT_EXTS:
        print(f"warn: unsupported file type, skipping: {path}", file=sys.stderr)
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
        return None


# ── TF-IDF index ───────────────────────────────────────────────────────────


def _tfidf_vectors(
    docs_tokens: List[List[str]],
) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    """Build L2-normalized TF-IDF vectors + the idf table for a chunk corpus."""
    n = len(docs_tokens)
    df: Counter = Counter()
    for toks in docs_tokens:
        for term in set(toks):
            df[term] += 1
    idf = {term: math.log((n + 1) / (freq + 1)) + 1.0 for term, freq in df.items()}

    vectors: List[Dict[str, float]] = []
    for toks in docs_tokens:
        counts = Counter(toks)
        vec = {t: (1.0 + math.log(c)) * idf[t] for t, c in counts.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vectors.append({t: w / norm for t, w in vec.items()})
    return vectors, idf


def _cosine(query_vec: Dict[str, float], doc_vec: Dict[str, float]) -> float:
    """Dot product of two L2-normalized sparse vectors (== cosine)."""
    # Iterate the smaller vector for speed.
    if len(query_vec) > len(doc_vec):
        query_vec, doc_vec = doc_vec, query_vec
    return sum(w * doc_vec.get(t, 0.0) for t, w in query_vec.items())


def cmd_index(paths: List[str]) -> int:
    files = _iter_files(paths)
    if not files:
        print("no indexable files found", file=sys.stderr)
        return 1

    chunks: List[Dict] = []
    for path in files:
        text = _read_source(path)
        if text is None:
            continue
        for i, chunk in enumerate(chunk_text(text)):
            chunks.append({"source": str(path), "chunk": i, "text": chunk})

    if not chunks:
        print("no text extracted from the given paths", file=sys.stderr)
        return 1

    vectors, idf = _tfidf_vectors([tokenize(c["text"]) for c in chunks])
    for c, v in zip(chunks, vectors):
        c["vector"] = v

    payload = {"idf": idf, "chunks": chunks}
    out = _index_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    sources = sorted({c["source"] for c in chunks})
    print(f"indexed {len(chunks)} chunk(s) from {len(sources)} file(s) -> {out}")
    return 0


def cmd_query(text: str, k: int) -> int:
    idx = _index_path()
    if not idx.is_file():
        print("no index found — run `index <path>` first", file=sys.stderr)
        return 1
    payload = json.loads(idx.read_text(encoding="utf-8"))
    idf: Dict[str, float] = payload["idf"]
    chunks: List[Dict] = payload["chunks"]

    counts = Counter(tokenize(text))
    q = {t: (1.0 + math.log(c)) * idf.get(t, 0.0) for t, c in counts.items()}
    norm = math.sqrt(sum(w * w for w in q.values())) or 1.0
    q = {t: w / norm for t, w in q.items() if w}

    scored = sorted(
        ((_cosine(q, c["vector"]), c) for c in chunks),
        key=lambda pair: pair[0],
        reverse=True,
    )[: max(1, k)]

    hits = [(s, c) for s, c in scored if s > 0]
    if not hits:
        print("no relevant chunks found")
        return 0

    for rank, (score, c) in enumerate(hits, 1):
        snippet = " ".join(c["text"].split())
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        print(f"[{rank}] score={score:.3f}  {c['source']}#chunk{c['chunk']}")
        print(f"    {snippet}\n")
    return 0


def cmd_list() -> int:
    idx = _index_path()
    if not idx.is_file():
        print("index empty (no index.json)")
        return 0
    payload = json.loads(idx.read_text(encoding="utf-8"))
    chunks = payload.get("chunks", [])
    sources: Counter = Counter(c["source"] for c in chunks)
    print(f"{len(chunks)} chunk(s) across {len(sources)} file(s):")
    for src, n in sorted(sources.items()):
        print(f"  {n:>4}  {src}")
    return 0


def cmd_reset() -> int:
    idx = _index_path()
    if idx.exists():
        idx.unlink()
        print(f"removed {idx}")
    else:
        print("nothing to reset")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rag", description="Local TF-IDF RAG retriever.")
    sub = p.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Index a folder and/or files.")
    p_index.add_argument("paths", nargs="+", help="Directories (crawled) and/or files.")

    p_query = sub.add_parser("query", help="Retrieve top chunks for a question.")
    p_query.add_argument("text", help="The query string.")
    p_query.add_argument("--k", type=int, default=5, help="Number of results (default 5).")

    sub.add_parser("list", help="Show what is indexed.")
    sub.add_parser("reset", help="Delete the index.")
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "index":
        return cmd_index(args.paths)
    if args.command == "query":
        return cmd_query(args.text, args.k)
    if args.command == "list":
        return cmd_list()
    if args.command == "reset":
        return cmd_reset()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
