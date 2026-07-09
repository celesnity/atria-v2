---
name: tasco_jarvis_map
description: Vietnam places map (HCMC/Hanoi/Da Nang) — POI search with abbreviation/no-accent matching, nearby search, address geocoding, and the Jarvis map dashboard.
---

# Tasco Jarvis Map

Interactive Leaflet map over the AI Maps Vietnam dataset (190 POIs, 150
addresses, abbreviation dictionary) with a Jarvis AI copilot panel. The
search engine understands Vietnamese query quirks: missing accents
("quan ca phe"), abbreviations ("q1" → "Quận 1", "tp hcm"), aliases and
mixed EN/VN ("ben thanh market").

Every query is classified by an intent router (`scripts/query_intent.py`,
data-derived — no hardcoded places or brands) into the competition archetypes:
POI / Category / Brand / Address / Nearby (proximity anchor or current
location) / Navigation / Coordinate / Ambiguous / Discovery. Proximity
("atm gần sân bay"), coordinate ("10.7769,106.7009"), navigation ("chỉ đường
đến …") and opening-hours ("mở cửa sau 10 giờ tối") queries are all handled;
the `search` response carries `intent`, `anchor`, `entities` and
`confidence_score` alongside the results. See `skills/search.md`.

Retrieval is GeoRAG-backed: PostgreSQL + PostGIS + pg_trgm + full-text +
pgvector hybrid scoring (dedicated `map-db` container), with automatic
fallback to the local JSON engine when the DB is down. City mentions
("saigon", "sg", "tphcm", "hanoi", "hn", "danang"…) are detected via a
gazetteer derived from the dataset at import time and applied as a HARD
filter — results never leak from another city. Never answer map facts
from memory — always call the tools below.

## When to use

- The user asks to find a place, address, or category of places in Ho Chi
  Minh City, Hanoi, or Da Nang (cafes, pharmacies, gas stations, malls,
  hospitals, banks, cinemas, supermarkets, EV chargers…).
- The user asks what is near a location or wants places within a radius.
- The user wants an address located (geocoded) on the map.
- The user gives coordinates and asks what place/address is there
  (reverse geocoding).
- The user wants a data-quality audit of the POI dataset (duplicate
  detection) or asks WHY a search returned/ranked a specific place.

## How to use

All commands print a single JSON object to stdout. Bash CWD is the chat
workspace, so always use absolute paths:

```bash
# Find places (handles no-accent/abbreviated/mixed-language queries)
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" search "cafe q1" --limit 8

# Places near a coordinate (optionally one category)
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" near --lat 10.7725 --lng 106.698 --radius-km 2 --category pharmacy

# Locate an address or named place
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" geocode "283 nguyen hue q7"

# Category keys + counts
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" categories

# What is at these coordinates? (nearest known place/address)
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" reverse_geocode --lat 10.7726 --lng 106.6981

# Audit the dataset for duplicate POIs
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" find_duplicates --threshold 0.75

# Explain why a POI matches (per-signal score breakdown)
python "D:/[Project]_atriaV2/modules/tasco_jarvis_map/scripts/search.py" explain_match "cafe q1" --poi-id POI013
```

Full flag reference and JSON shapes: sub-skill `tasco_jarvis_map:search`.

Answer strictly from the returned JSON — never invent places, addresses,
or coordinates that are not in a result.
