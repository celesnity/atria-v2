# Ingest drop-folder — maintenance_copilot

Drop maintenance documents here. On **module startup** they are chunked,
embedded, and upserted into the vector store (qdrant) automatically — no rebuild
needed. Add/edit files, then restart the module:

```bash
docker compose restart maintenance-copilot
# or force a re-ingest without restart:
docker compose exec maintenance-copilot sh -c 'cd /app/pipeline && python copilot.py ingest --samples /app/ingest_data'
```

Startup ingest is **idempotent** (chunks get stable ids, so re-ingesting an
unchanged file is a no-op) and **resilient** (it waits for the embedding sidecar
to come up, and skips malformed files instead of aborting the batch).

## Required file format

Only `.md` / `.txt` files **directly in this folder** are ingested (not
subfolders). Files whose name starts with `_` or `.` (like this README) are
ignored. Each document MUST begin with a YAML front-matter block declaring:

```markdown
---
doc_type: MEL            # AMM | MEL | CDL | TSM | ...
title: MEL 32-31 Landing Gear
revision: Rev 12
effective_date: 2026-01-15
ata_chapter: 32
---

# MEL 32-31-01 — Antiskid Inoperative

Body text of the procedure / item… headings and paragraphs become chunks.
```

Missing any required key => the file is skipped (logged), the rest still ingest.

## Controls (env)

- `MC_INGEST_ON_STARTUP=1` — enable startup ingest (default on). Set `0` to disable.
- `MC_INGEST_DIR=/app/ingest_data` — folder ingested (this mount).

See `sample_mel_32.md` in this folder for a working example.

> Note: `LLM_INGEST_production.md` (in Downloads) is the design reference for
> LLM-assisted ingest. Its own benchmark shows deterministic chunk+id ingest
> beats LLM-invented "relatedness" edges, which is why this pipeline keeps
> structuring deterministic. Keep meta/spec docs out of this corpus folder.
