"""Data-driven place gazetteer — no place name is hardcoded anywhere.

Admin-area knowledge (cities, districts and every alias/abbreviation for
them) is DERIVED from the dataset each time it is loaded/imported:

  1. distinct `city` / `district` values from pois.json + addresses.json;
  2. deterministic variant generation per name:
       - folded form                      ("TP Hồ Chí Minh" -> "tp ho chi minh")
       - generic admin-prefix strip       (-> "ho chi minh") + re-prefixed twins
         ("thanh pho ho chi minh", "tp ho chi minh") so dataset spellings and
         abbreviation expansions unify. The prefix list is generic Vietnamese
         administrative vocabulary — a language-level constant like fold()'s
         đ->d — NOT place data.
       - no-space concatenation           ("sai gon" -> "saigon", "ha noi" -> "hanoi")
  3. abbreviation mining over data/abbreviations.json: an expansion's
     '/'-separated alternatives are alias links; if any alternative matches a
     known variant of an entry, the term and all other alternatives (plus
     their no-space forms) join that entry ("sg" -> "sai gon / thanh pho ho
     chi minh" links sg, sai gon and saigon to TP Hồ Chí Minh);
  4. optional data/place_aliases.json seed for exonyms genuinely absent from
     the data ({"aliases": [{"name": "<data value>", "alias": "..."}]}).

New cities/countries in future datasets therefore work with ZERO code
changes: re-run the import (db) / restart the script (json engine).

detect_place() scans CITY-level variants only. Districts are derived and
stored (map_admin_areas) for inspection and future tools, but district
phrases are deliberately NOT consumed from the query: district names can
double as street names ("Hai Bà Trưng" street vs district), and the existing
remainder/location scoring already handles districts well.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import DATA_DIR, fold, load_abbreviations, load_json

# Generic Vietnamese administrative prefixes (language-level constants).
# Longest first so "thanh pho" wins over "tp"-as-token scans.
ADMIN_PREFIXES = ("thanh pho", "thi xa", "quan", "huyen", "phuong", "tinh", "tp", "tx", "q", "p")
# Re-prefix twins emitted for the stripped form so "tp X" (dataset) and
# "thanh pho X" (abbreviation expansions) resolve to the same entry.
PREFIX_TWINS = {"tp": "thanh pho", "thanh pho": "tp", "q": "quan", "quan": "q"}


def _strip_prefix(folded: str) -> tuple[str, str | None]:
    """('tp ho chi minh') -> ('ho chi minh', 'tp'); no prefix -> (input, None)."""
    for pre in ADMIN_PREFIXES:
        if folded.startswith(pre + " "):
            return folded[len(pre) + 1 :], pre
    return folded, None


def _usable(variant: str) -> bool:
    """Variant sanity: >=2 chars and not purely numeric (a bare '1' stripped
    from 'quan 1' would false-match any query containing the token '1')."""
    v = variant.strip()
    return len(v) >= 2 and any(ch.isalpha() for ch in v)


def _nospace(variant: str) -> str | None:
    if " " not in variant:
        return None
    joined = variant.replace(" ", "")
    return joined if _usable(joined) else None


def build_gazetteer(
    pois: list[dict],
    addresses: list[dict],
    terms: dict[str, str],
    seed_aliases: list[dict] | None = None,
) -> dict:
    """Derive the place gazetteer from already-loaded dataset structures.

    Returns {"entries": [entry], "city_idx": {variant: entry}} where entry =
    {level, canonical, name, parent_city, variants: {variant: source}}.
    canonical = prefix-stripped folded name (a substring of fold(city), which
    is what the hard filter tests against).
    """
    entries: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}  # (level, canonical) -> entry

    def add_variant(entry: dict, variant: str, source: str) -> None:
        variant = variant.strip()
        if _usable(variant) and variant not in entry["variants"]:
            entry["variants"][variant] = source

    def add_name(level: str, name: str, parent_city: str | None) -> None:
        folded = fold(name)
        stripped, pre = _strip_prefix(folded)
        canonical = stripped if _usable(stripped) else folded
        key = (level, canonical)
        entry = by_key.get(key)
        if entry is None:
            entry = {
                "level": level,
                "canonical": canonical,
                "name": name,
                "parent_city": parent_city,
                "variants": {},
            }
            by_key[key] = entry
            entries.append(entry)
        add_variant(entry, folded, "data")
        if _usable(stripped) and stripped != folded:
            add_variant(entry, stripped, "prefix")
        if pre and PREFIX_TWINS.get(pre) and _usable(stripped):
            add_variant(entry, PREFIX_TWINS[pre] + " " + stripped, "prefix")
        for v in list(entry["variants"]):
            ns = _nospace(v)
            if ns:
                add_variant(entry, ns, "nospace")

    for row in list(pois) + list(addresses):
        if row.get("city"):
            add_name("city", row["city"], None)
    for row in list(pois) + list(addresses):
        if row.get("district"):
            add_name("district", row["district"], row.get("city"))

    # Abbreviation mining: '/'-separated expansion alternatives are alias links.
    for term, expansion in (terms or {}).items():
        alts = [fold(a) for a in str(expansion).split("/")]
        alts = [a for a in alts if a]
        hit = None
        for entry in entries:
            if any(a in entry["variants"] for a in alts):
                hit = entry
                break
        if hit is None:
            continue
        for v in [fold(term), *alts]:
            add_variant(hit, v, "abbrev")
            ns = _nospace(v)
            if ns:
                add_variant(hit, ns, "abbrev")

    # Optional seed file for exonyms not derivable from the data.
    for row in seed_aliases or []:
        name, alias = row.get("name"), row.get("alias")
        if not name or not alias:
            continue
        folded_name = fold(name)
        for entry in entries:
            if folded_name in entry["variants"] or fold(entry["name"]) == folded_name:
                add_variant(entry, fold(alias), "seed")
                ns = _nospace(fold(alias))
                if ns:
                    add_variant(entry, ns, "seed")
                break

    # City detection index. On variant collisions the longer canonical loses
    # (deterministic); collisions don't exist in current data.
    city_idx: dict[str, dict] = {}
    for entry in entries:
        if entry["level"] != "city":
            continue
        for v in entry["variants"]:
            city_idx.setdefault(v, entry)

    return {"entries": entries, "city_idx": city_idx}


def load_seed_aliases() -> list[dict]:
    path = DATA_DIR / "place_aliases.json"
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("aliases", [])


def build_from_data() -> dict:
    """Build straight from the module's data files (json-engine path)."""
    pois = load_json("pois.json")["pois"]
    addresses = load_json("addresses.json")["addresses"]
    terms, _ = load_abbreviations()
    return build_gazetteer(pois, addresses, terms, load_seed_aliases())


def detect_place(norm: str, gaz: dict) -> tuple[dict | None, str]:
    """Find the longest CITY variant inside the normalized query (padded
    substring scan, same technique as search._detect_category). On a hit,
    remove ALL variant occurrences of that city — this cleans multi-alias
    expansions like sg -> 'sai gon / thanh pho ho chi minh' in one pass.
    Returns (entry | None, remainder)."""
    padded = f" {norm} "
    best_phrase, best_entry = "", None
    for phrase, entry in gaz["city_idx"].items():
        if f" {phrase} " in padded and len(phrase) > len(best_phrase):
            best_phrase, best_entry = phrase, entry
    if best_entry is None:
        return None, norm
    for phrase in sorted(best_entry["variants"], key=len, reverse=True):
        padded = padded.replace(f" {phrase} ", " ")
    return best_entry, padded.strip()


def resolve_place(value: str | None, gaz: dict) -> str | None:
    """Map a --city argument through the gazetteer ('saigon' -> 'ho chi minh').
    Unknown values pass through folded (legacy substring-filter behavior)."""
    if not value:
        return None
    folded = fold(value)
    entry = gaz["city_idx"].get(folded)
    return entry["canonical"] if entry else folded


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect the derived place gazetteer")
    ap.add_argument("--dump", action="store_true", help="print the derived table")
    ap.parse_args()
    gaz = build_from_data()
    out = [
        {
            "level": e["level"],
            "canonical": e["canonical"],
            "name": e["name"],
            "parent_city": e["parent_city"],
            "variants": {v: s for v, s in sorted(e["variants"].items())},
        }
        for e in gaz["entries"]
    ]
    print(json.dumps({"entries": out, "count": len(out)}, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
