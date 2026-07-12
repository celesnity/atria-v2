"""Generate pgvector embeddings for POIs and addresses (OpenAI, idempotent).

Reads rows from map-db (run db_import.py first), builds embedding_text from
the RAW ACCENTED fields (diacritics carry semantic signal — folding is a
lexical-side concern), and upserts into map_embeddings. Rows whose
sha256(model + '\\0' + embedding_text) already matches are skipped, so
re-running is free; --force regenerates everything.

Missing OPENAI_API_KEY -> exits 0 with a "skipped" notice (embeddings are an
enhancement; hybrid search renormalizes weights without the vector signal).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
from _data import emit

BATCH_SIZE = 512


def _hash(model: str, text: str) -> str:
    return hashlib.sha256((model + "\0" + text).encode("utf-8")).hexdigest()


def _poi_text(raw: dict, cat: dict | None) -> str:
    name = raw["name"]
    if raw.get("name_en") and raw["name_en"] != name:
        name += f" / {raw['name_en']}"
    category = raw.get("category", "")
    if cat:
        category = f"{cat['label']} ({cat['label_vi']})"
    # sub_category carries the semantic head an implicit-category query keys on
    # ("Rooftop"/"Resort"/"Phở") — put it next to the category so the vector
    # binds those meanings even when they never appear in the POI name.
    if raw.get("sub_category"):
        category = f"{category} - {raw['sub_category']}"
    lines = [f"Name: {name}", f"Category: {category}"]
    if raw.get("brand"):
        lines.append(f"Brand: {raw['brand']}")
    addr = ", ".join(x for x in [raw.get("address"), raw.get("district"), raw.get("city")] if x)
    lines.append(f"Address: {addr}")
    if raw.get("aliases"):
        lines.append(f"Aliases: {', '.join(raw['aliases'])}")
    # Track-2 enrichment (accented — diacritics carry semantic signal). These are
    # the amenity/description surfaces that make "quán yên tĩnh để làm việc" or
    # "resort sang chảnh" retrievable by meaning rather than by name overlap.
    attrs = raw.get("attributes") or []
    tags = raw.get("tags") or []
    if attrs:
        lines.append(f"Attributes: {', '.join(attrs)}")
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    if raw.get("description"):
        lines.append(f"Description: {raw['description']}")
    return "\n".join(lines)


def _address_text(raw: dict) -> str:
    lines = [f"Address: {raw['full_address']}"]
    street = " ".join(x for x in [raw.get("house_number"), raw.get("street")] if x)
    parts = ", ".join(
        x for x in [street, raw.get("ward"), raw.get("district"), raw.get("city")] if x
    )
    if parts:
        lines.append(f"Street: {parts}")
    if raw.get("aliases"):
        lines.append(f"Aliases: {', '.join(raw['aliases'])}")
    if raw.get("notes"):
        lines.append(f"Notes: {raw['notes']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate map embeddings (OpenAI)")
    parser.add_argument("--force", action="store_true", help="regenerate all embeddings")
    args = parser.parse_args()

    api_key = _db.env_get("OPENAI_API_KEY")
    if not api_key:
        emit({"skipped": "no OPENAI_API_KEY", "embedded": 0})
        return

    try:
        conn = _db.connect()
    except _db.MapDbUnavailable as exc:
        emit({"error": f"map-db unavailable: {exc}"})
        sys.exit(1)

    model = _db.EMBED_MODEL
    with conn, conn.cursor() as cur:
        cur.execute("SELECT key, label, label_vi FROM map_categories")
        cats = {k: {"label": lb, "label_vi": lv} for k, lb, lv in cur.fetchall()}
        cur.execute("SELECT poi_id, raw FROM map_pois ORDER BY poi_id")
        items = [
            ("poi", pid, _poi_text(raw, cats.get(raw.get("category"))))
            for pid, raw in cur.fetchall()
        ]
        cur.execute("SELECT address_id, raw FROM map_addresses ORDER BY address_id")
        items += [("address", aid, _address_text(raw)) for aid, raw in cur.fetchall()]

        cur.execute("SELECT entity_type, entity_id, text_hash FROM map_embeddings")
        existing = {(t, i): h for t, i, h in cur.fetchall()}

        pending = [
            (etype, eid, text, _hash(model, text))
            for etype, eid, text in items
            if args.force or existing.get((etype, eid)) != _hash(model, text)
        ]

        embedded = 0
        if pending:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            for start in range(0, len(pending), BATCH_SIZE):
                batch = pending[start : start + BATCH_SIZE]
                resp = client.embeddings.create(model=model, input=[t for _, _, t, _ in batch])
                for (etype, eid, text, thash), datum in zip(batch, resp.data):
                    cur.execute(
                        """INSERT INTO map_embeddings (entity_type, entity_id, embedding,
                               embedding_text, text_hash, model, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, now())
                           ON CONFLICT (entity_type, entity_id) DO UPDATE SET
                               embedding=EXCLUDED.embedding,
                               embedding_text=EXCLUDED.embedding_text,
                               text_hash=EXCLUDED.text_hash, model=EXCLUDED.model,
                               updated_at=now()""",
                        (etype, eid, datum.embedding, text, thash, model),
                    )
                    embedded += 1

    emit({"embedded": embedded, "skipped": len(items) - embedded, "model": model})


if __name__ == "__main__":
    main()
