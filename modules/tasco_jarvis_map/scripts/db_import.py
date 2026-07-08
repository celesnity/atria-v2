"""Full-sync importer: data/pois.json + data/addresses.json -> map-db.

The JSON files stay the source of truth (v1); the DB is a derived index.
Re-run any time after editing the JSON (then gen_embeddings.py).

- normalized_* columns take the dataset's precomputed q{} keys VERBATIM (they
  were built with _data.fold/expand_abbrev — byte-identical to query-time
  normalization). fold() is re-run only as a consistency assertion (warns).
- raw jsonb keeps the original object verbatim (the `pois` dump emits it).
- Aliases: rank 0 = primary name/name_en (or full_address), rank 1 = dataset
  aliases. Raw accented form matched to its normalized q-alias by folding.
- Deletes rows whose ids vanished from the JSON (true full sync).

Prints one JSON summary to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
import gazetteer
from _data import emit, expand_abbrev, fold, load_abbreviations, load_json


def _norm(text: str, terms, max_ngram) -> str:
    return expand_abbrev(fold(text), terms, max_ngram)


def _alias_rows(entity_type, entity_id, primary_pairs, raw_aliases, q_aliases, terms, max_ngram):
    """Yield (entity_type, entity_id, alias, normalized_alias, rank) rows.

    primary_pairs: [(raw, normalized)] for rank-0 keys (name/name_en/full).
    q_aliases is a sorted/deduped set, so raw aliases are matched by folding
    rather than by index; unmatched normalized forms fall back to themselves.
    """
    rows = {}
    for raw, norm in primary_pairs:
        if norm:
            rows.setdefault(norm, (raw or norm, 0))
    raw_by_norm = {_norm(a, terms, max_ngram): a for a in raw_aliases if a}
    for qa in q_aliases:
        if qa and qa not in rows:
            rows[qa] = (raw_by_norm.get(qa, qa), 1)
    for norm, (raw, rank) in rows.items():
        yield (entity_type, entity_id, raw, norm, rank)


def main() -> None:
    terms, max_ngram = load_abbreviations()
    pois_doc = load_json("pois.json")
    addr_doc = load_json("addresses.json")
    pois, categories = pois_doc["pois"], pois_doc["categories"]
    addresses = addr_doc["addresses"]

    warnings = []
    for p in pois:
        if _norm(p["name"], terms, max_ngram) != p["q"]["name"]:
            warnings.append(f"fold drift poi {p['poi_id']}")
    for a in addresses:
        if _norm(a["full_address"], terms, max_ngram) != a["q"]["full"]:
            warnings.append(f"fold drift address {a['address_id']}")

    try:
        conn = _db.connect()
    except _db.MapDbUnavailable as exc:
        emit({"error": f"map-db unavailable: {exc}"})
        sys.exit(1)

    alias_count = 0
    with conn, conn.cursor() as cur:
        for key, c in categories.items():
            cur.execute(
                """INSERT INTO map_categories (key, label, label_vi, color, emoji)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (key) DO UPDATE SET label=EXCLUDED.label,
                       label_vi=EXCLUDED.label_vi, color=EXCLUDED.color,
                       emoji=EXCLUDED.emoji""",
                (key, c["label"], c["label_vi"], c.get("color"), c.get("emoji")),
            )

        for p in pois:
            q = p["q"]
            name_blob = " ".join(
                x for x in [q["name"], q.get("name_en", ""), *q.get("aliases", [])] if x
            )
            cur.execute(
                """INSERT INTO map_pois (poi_id, name, name_en, category, brand, address,
                       district, city, lat, lng, rating, opening_hours,
                       normalized_name, normalized_name_en, normalized_address, name_blob,
                       geom, raw, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s::jsonb, now())
                   ON CONFLICT (poi_id) DO UPDATE SET
                       name=EXCLUDED.name, name_en=EXCLUDED.name_en,
                       category=EXCLUDED.category, brand=EXCLUDED.brand,
                       address=EXCLUDED.address, district=EXCLUDED.district,
                       city=EXCLUDED.city, lat=EXCLUDED.lat, lng=EXCLUDED.lng,
                       rating=EXCLUDED.rating, opening_hours=EXCLUDED.opening_hours,
                       normalized_name=EXCLUDED.normalized_name,
                       normalized_name_en=EXCLUDED.normalized_name_en,
                       normalized_address=EXCLUDED.normalized_address,
                       name_blob=EXCLUDED.name_blob, geom=EXCLUDED.geom,
                       raw=EXCLUDED.raw, updated_at=now()""",
                (
                    p["poi_id"],
                    p["name"],
                    p.get("name_en") or None,
                    p["category"],
                    p.get("brand") or None,
                    p.get("address"),
                    p.get("district"),
                    p.get("city"),
                    p["lat"],
                    p["lng"],
                    p.get("rating"),
                    p.get("opening_hours") or None,
                    q["name"],
                    q.get("name_en") or None,
                    q.get("addr") or None,
                    name_blob,
                    p["lng"],
                    p["lat"],
                    json.dumps(p, ensure_ascii=False),
                ),
            )

        for a in addresses:
            q = a["q"]
            cur.execute(
                """INSERT INTO map_addresses (address_id, full_address, house_number,
                       street, ward, district, city, lat, lng, notes,
                       normalized_full, geom, raw, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s::jsonb, now())
                   ON CONFLICT (address_id) DO UPDATE SET
                       full_address=EXCLUDED.full_address,
                       house_number=EXCLUDED.house_number, street=EXCLUDED.street,
                       ward=EXCLUDED.ward, district=EXCLUDED.district,
                       city=EXCLUDED.city, lat=EXCLUDED.lat, lng=EXCLUDED.lng,
                       notes=EXCLUDED.notes, normalized_full=EXCLUDED.normalized_full,
                       geom=EXCLUDED.geom, raw=EXCLUDED.raw, updated_at=now()""",
                (
                    a["address_id"],
                    a["full_address"],
                    a.get("house_number") or None,
                    a.get("street") or None,
                    a.get("ward") or None,
                    a.get("district"),
                    a.get("city"),
                    a["lat"],
                    a["lng"],
                    a.get("notes") or None,
                    q["full"],
                    a["lng"],
                    a["lat"],
                    json.dumps(a, ensure_ascii=False),
                ),
            )

        # Aliases: rebuild wholesale (cheap at this scale, avoids diffing).
        cur.execute("DELETE FROM map_aliases")
        for p in pois:
            q = p["q"]
            rows = _alias_rows(
                "poi",
                p["poi_id"],
                [(p["name"], q["name"]), (p.get("name_en", ""), q.get("name_en", ""))],
                p.get("aliases", []),
                q.get("aliases", []),
                terms,
                max_ngram,
            )
            for row in rows:
                cur.execute(
                    """INSERT INTO map_aliases (entity_type, entity_id, alias,
                           normalized_alias, rank) VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (entity_type, entity_id, normalized_alias) DO NOTHING""",
                    row,
                )
                alias_count += 1
        for a in addresses:
            q = a["q"]
            rows = _alias_rows(
                "address",
                a["address_id"],
                [(a["full_address"], q["full"])],
                a.get("aliases", []),
                q.get("aliases", []),
                terms,
                max_ngram,
            )
            for row in rows:
                cur.execute(
                    """INSERT INTO map_aliases (entity_type, entity_id, alias,
                           normalized_alias, rank) VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (entity_type, entity_id, normalized_alias) DO NOTHING""",
                    row,
                )
                alias_count += 1

        # Derived place gazetteer -> map_admin_areas (full rebuild; this is
        # where place knowledge enters the DB — see scripts/gazetteer.py).
        gaz = gazetteer.build_gazetteer(pois, addresses, terms, gazetteer.load_seed_aliases())
        cur.execute("DELETE FROM map_admin_areas")
        for entry in gaz["entries"]:
            for variant, source in entry["variants"].items():
                cur.execute(
                    """INSERT INTO map_admin_areas
                           (level, canonical, name, parent_city, variant, source)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (level, canonical, variant) DO NOTHING""",
                    (
                        entry["level"],
                        entry["canonical"],
                        entry["name"],
                        entry["parent_city"],
                        variant,
                        source,
                    ),
                )

        # Full sync: drop rows whose ids vanished from the JSON.
        poi_ids = [p["poi_id"] for p in pois]
        addr_ids = [a["address_id"] for a in addresses]
        cur.execute("DELETE FROM map_pois WHERE NOT (poi_id = ANY(%s))", (poi_ids,))
        cur.execute("DELETE FROM map_addresses WHERE NOT (address_id = ANY(%s))", (addr_ids,))
        cur.execute(
            """DELETE FROM map_embeddings e WHERE
               (e.entity_type='poi' AND NOT (e.entity_id = ANY(%s))) OR
               (e.entity_type='address' AND NOT (e.entity_id = ANY(%s)))""",
            (poi_ids, addr_ids),
        )

        cur.execute("SELECT count(*) FROM map_pois")
        n_pois = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM map_addresses")
        n_addr = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM map_aliases")
        n_alias = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM map_categories")
        n_cat = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM map_admin_areas")
        n_admin = cur.fetchone()[0]

    out = {
        "pois": n_pois,
        "addresses": n_addr,
        "aliases": n_alias,
        "categories": n_cat,
        "admin_areas": n_admin,
    }
    if warnings:
        out["warnings"] = warnings[:20]
    emit(out)


if __name__ == "__main__":
    main()
