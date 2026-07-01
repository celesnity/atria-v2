---
name: rag
description: Local retrieval-augmented generation over your own docs, including PDFs. Index a folder and/or individual files (text or PDF) into a TF-IDF store, then retrieve the most relevant chunks for a question. No embeddings API — fully offline and reproducible; PDFs are extracted to text automatically. Use when the user asks to search, ground answers in, summarize, or "ask questions about" a set of local files or PDFs.
---

# rag

A small **retrieval** engine over local text. It indexes files into a TF-IDF
vector store (`data/index.json`) and returns the top matching chunks for a
query. Retrieval only — you (the agent) do the "generation" by reading the
returned chunks and answering the user, citing the `source#chunkN` markers.

Everything is pure Python: no embeddings API, no `OPENAI_API_KEY`, no extra
dependencies. Runs offline and deterministically.

## When to use

Use this when the user wants to **ground answers in a specific set of local
files** — "index these docs and answer questions from them", "search my notes
folder", "what do these files say about X". For a one-off grep, prefer the
normal search tools; reach for `rag` when the same corpus is queried repeatedly
or when semantic-ish ranking (not exact string match) is wanted.

## How to use

Absolute paths. Let `<r>` = `python <modules>/rag/scripts/rag.py`
(`<modules>` resolves to the active modules directory — see the SKILL block
header in the system prompt).

Index a directory (crawled recursively) and/or explicit files — both are
accepted in one call:

```
<r> index /path/to/docs
<r> index /path/to/a.md /path/to/b.txt
<r> index /path/to/docs extra_notes.md
```

Retrieve the most relevant chunks for a question (default 5, tune with `--k`):

```
<r> query "how does the module registry decide what to load?" --k 5
```

Inspect / clear the index:

```
<r> list
<r> reset
```

Typical flow: run `index` once on the corpus, then answer each user question by
running `query`, reading the returned chunks, and replying with citations to
the printed `source#chunkN` markers.

## What gets indexed

Text files: `.md`, `.txt`, `.rst`, `.py`, `.js`/`.ts`, `.json`, `.yaml`,
`.html`, `.css`, `.csv`, and similar — **plus `.pdf`**. PDFs are extracted to
text via the first available backend: poppler's `pdftotext` CLI, then `pypdf`,
then PyMuPDF (`pypdf` is auto-installed via the module's `requirements.txt`).
A scanned/image-only PDF with no text layer is skipped with a warning (no OCR).
Other binaries are skipped. Everything is split into ~1000-character
overlapping chunks on paragraph boundaries.

So to answer questions about a PDF: `index` the PDF (or its folder), then
`query` as usual — no manual conversion needed.

## Data model

- `data/index.json` — the whole store: an `idf` table plus one entry per chunk
  (`source`, `chunk` index, `text`, and its L2-normalized sparse TF-IDF
  `vector`). Query ranking is cosine similarity against these vectors.

Override the index location with `ATRIA_RAG_DIR`.

## Files

- `SKILL.md` — this overview.
- `scripts/rag.py` — the CLI: `index`, `query`, `list`, `reset`.
- `requirements.txt` — optional `pypdf` for PDF text extraction (auto-installed).
- `data/index.json` — the TF-IDF store (auto-created; gitignored).
