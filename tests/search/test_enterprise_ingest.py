"""Chunker unit tests and (live) ingestion integration test for Track 1."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "modules" / "enterprise_search"))
from chunking import chunk_markdown  # noqa: E402

XLSX = (
    Path(__file__).resolve().parents[2]
    / "mobility/track1/ai_workspace_dataset_vietnamese_participants.xlsx"
)


def test_chunk_short_text_is_single_chunk():
    assert chunk_markdown("ngắn gọn") == ["ngắn gọn"]


def test_chunk_splits_on_blank_lines_and_packs():
    paras = [f"đoạn văn số {i}: " + "nội dung " * 15 for i in range(12)]
    text = "\n\n".join(paras)
    chunks = chunk_markdown(text, max_chars=400)
    assert len(chunks) > 1
    assert all(len(c) <= 400 + 200 for c in chunks)  # single paragraphs may overflow slightly
    joined = "\n\n".join(chunks)
    for para in paras:
        assert para.strip() in joined  # every paragraph survives intact, exactly once each
    assert joined.count("đoạn văn số 3:") == 1


def test_chunk_preserves_all_content():
    text = "a\n\nb\n\nc"
    assert " ".join(chunk_markdown(text, max_chars=3)).split() == ["a", "b", "c"]


@pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and (os.environ.get("SEARCH_EMBED_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        and XLSX.exists()
    ),
    reason="needs live Postgres, Qdrant, an embedding key and the Track 1 xlsx",
)
def test_ingest_end_to_end():
    from minder.core.context_engineering.search import pg

    script = Path(__file__).resolve().parents[2] / "modules/enterprise_search/scripts/ingest.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--xlsx", str(XLSX)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    docs = pg.fetch_all("SELECT count(*) AS n FROM enterprise_documents")[0]["n"]
    chunks = pg.fetch_all("SELECT count(*) AS n FROM enterprise_chunks")[0]["n"]
    users = pg.fetch_all("SELECT count(*) AS n FROM enterprise_users")[0]["n"]
    assert docs == 40
    assert chunks >= docs
    assert users > 0
    # idempotency: second run must not change counts
    proc2 = subprocess.run(
        [sys.executable, str(script), "--xlsx", str(XLSX)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc2.returncode == 0, proc2.stderr
    assert pg.fetch_all("SELECT count(*) AS n FROM enterprise_chunks")[0]["n"] == chunks
