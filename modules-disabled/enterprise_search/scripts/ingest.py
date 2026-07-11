"""Ingest the Track 1 enterprise xlsx into Postgres + Qdrant (idempotent).

Usage:
    python modules/enterprise_search/scripts/ingest.py \
        --xlsx mobility/track1/ai_workspace_dataset_vietnamese_participants.xlsx

Reads corpus sheets only (Documents, Document_Metadata, Users). The held-out
evaluation sheet is never opened here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for chunking
from chunking import chunk_markdown  # noqa: E402

# Repo root, so `atria` resolves when this file is run directly (as a script,
# rather than through a test runner that already puts the repo root on
# sys.path). Needed regardless of whether atria is pip-installed editable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from atria.core.context_engineering.search import pg  # noqa: E402
from atria.core.context_engineering.search.dense import DenseIndex  # noqa: E402
from atria.core.context_engineering.search.embedder import Embedder  # noqa: E402
from atria.core.context_engineering.search.normalize import normalize_for_search  # noqa: E402

COLLECTION = "enterprise_chunks"
_HEADER_ROW_OFFSET = 2  # sheets: title row, blank row, header row, data...

_DDL = [
    """CREATE TABLE IF NOT EXISTS enterprise_users(
        user_id text PRIMARY KEY, full_name text, department text,
        role text, email text, status text)""",
    """CREATE TABLE IF NOT EXISTS enterprise_documents(
        document_id text PRIMARY KEY, title text, department text,
        classification text, owner text, tags text, last_updated text,
        language text, content text)""",
    """CREATE TABLE IF NOT EXISTS enterprise_chunks(
        chunk_id text PRIMARY KEY,
        document_id text REFERENCES enterprise_documents(document_id) ON DELETE CASCADE,
        title text, department text, classification text, chunk_index int,
        content text, content_norm text,
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content_norm)) STORED)""",
    "CREATE INDEX IF NOT EXISTS enterprise_chunks_tsv_idx ON enterprise_chunks USING gin(tsv)",
]


def _sheet_rows(workbook: Any, name: str) -> list[dict[str, Any]]:
    """Read a Track 1 sheet into dicts keyed by its header row.

    Track 1 sheets share a fixed layout: a title row, a blank row, a header
    row, then data rows. This skips straight to the header row (row index
    `_HEADER_ROW_OFFSET`) and zips each subsequent data row against it,
    skipping any fully-blank rows.

    Args:
        workbook: An open openpyxl Workbook (or any object supporting
            `workbook[name]` indexing to a worksheet).
        name: Name of the sheet to read (e.g. "Documents", "Users").

    Returns:
        One dict per data row, mapping header column name to cell value.
        Row order matches the sheet's original row order.
    """
    sheet = workbook[name]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c) for c in rows[_HEADER_ROW_OFFSET]]
    out = []
    for raw in rows[_HEADER_ROW_OFFSET + 1 :]:
        if raw is None or all(c is None for c in raw):
            continue
        out.append({header[i]: raw[i] for i in range(len(header))})
    return out


def main() -> None:
    """Ingest the Track 1 xlsx into Postgres (users/documents/chunks) and Qdrant.

    Reads the `--xlsx` workbook's Documents, Document_Metadata, and Users
    sheets, creates the enterprise_* tables if missing, upserts users and
    documents, replaces each document's chunks, embeds the chunk texts, and
    upserts them into the Qdrant `enterprise_chunks` collection, then deletes
    any Qdrant points for chunk ids that no longer exist for a document (e.g.
    the document shrank to fewer chunks). Safe to re-run: all Postgres writes
    are upserts (or delete-then-insert for chunks) and the Qdrant upsert is
    keyed by a stable id derived from the chunk id, so repeated runs converge
    on the same state.

    Args:
        None. Arguments are parsed from `sys.argv` via argparse (`--xlsx`,
        the path to the Track 1 participants xlsx).

    Returns:
        None. Prints a one-line ingestion summary (document/chunk/user
        counts) to stdout on success.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, help="Path to the Track 1 participants xlsx")
    args = parser.parse_args()

    workbook = openpyxl.load_workbook(args.xlsx, read_only=True)
    documents = _sheet_rows(workbook, "Documents")
    metadata = {m["document_id"]: m for m in _sheet_rows(workbook, "Document_Metadata")}
    users = _sheet_rows(workbook, "Users")

    for ddl in _DDL:
        pg.execute(ddl)

    for user in users:
        pg.execute(
            """INSERT INTO enterprise_users(user_id, full_name, department, role, email, status)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (user_id) DO UPDATE SET full_name=EXCLUDED.full_name,
                 department=EXCLUDED.department, role=EXCLUDED.role,
                 email=EXCLUDED.email, status=EXCLUDED.status""",
            [
                user["user_id"],
                user["full_name"],
                user["department"],
                user["role"],
                user["email"],
                str(user.get("status", "")),
            ],
        )

    chunk_ids: list[str] = []
    chunk_texts: list[str] = []
    chunk_payloads: list[dict[str, Any]] = []
    previous_chunk_ids: set[str] = set()

    for doc in documents:
        doc_id = doc["document_id"]
        meta = metadata.get(doc_id, {})
        content = str(doc.get("content_vi") or "")
        pg.execute(
            """INSERT INTO enterprise_documents(document_id, title, department, classification,
                 owner, tags, last_updated, language, content)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               ON CONFLICT (document_id) DO UPDATE SET title=EXCLUDED.title,
                 department=EXCLUDED.department, classification=EXCLUDED.classification,
                 owner=EXCLUDED.owner, tags=EXCLUDED.tags, last_updated=EXCLUDED.last_updated,
                 language=EXCLUDED.language, content=EXCLUDED.content""",
            [
                doc_id,
                doc["title"],
                doc["department"],
                doc["classification"],
                str(meta.get("owner", "")),
                str(meta.get("tags", "")),
                str(meta.get("last_updated", "")),
                str(meta.get("language", "vi")),
                content,
            ],
        )
        previous_chunk_ids.update(
            row["chunk_id"]
            for row in pg.fetch_all(
                "SELECT chunk_id FROM enterprise_chunks WHERE document_id = $1", [doc_id]
            )
        )
        pg.execute("DELETE FROM enterprise_chunks WHERE document_id = $1", [doc_id])
        for index, chunk in enumerate(chunk_markdown(content)):
            chunk_id = f"{doc_id}#{index}"
            pg.execute(
                """INSERT INTO enterprise_chunks(chunk_id, document_id, title, department,
                     classification, chunk_index, content, content_norm)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                [
                    chunk_id,
                    doc_id,
                    doc["title"],
                    doc["department"],
                    doc["classification"],
                    index,
                    chunk,
                    normalize_for_search(f"{doc['title']} {chunk}"),
                ],
            )
            chunk_ids.append(chunk_id)
            chunk_texts.append(f"{doc['title']}\n{chunk}")
            chunk_payloads.append(
                {
                    "document_id": doc_id,
                    "title": doc["title"],
                    "department": doc["department"],
                    "classification": doc["classification"],
                }
            )

    embedder = Embedder()
    vectors = embedder.embed(chunk_texts)
    index = DenseIndex(COLLECTION)
    index.ensure(dim=len(vectors[0]))
    index.upsert(chunk_ids, vectors, chunk_payloads)
    stale = sorted(previous_chunk_ids - set(chunk_ids))
    index.delete(stale)
    print(
        f"ingested {len(documents)} documents, {len(chunk_ids)} chunks, "
        f"{len(users)} users into pg + qdrant:{COLLECTION}"
    )
    if stale:
        print(f"removed {len(stale)} stale point(s) from qdrant:{COLLECTION}")


if __name__ == "__main__":
    main()
