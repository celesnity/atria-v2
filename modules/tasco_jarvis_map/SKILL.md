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

## When to use

- The user asks to find a place, address, or category of places in Ho Chi
  Minh City, Hanoi, or Da Nang (cafes, pharmacies, gas stations, malls,
  hospitals, banks, cinemas, supermarkets, EV chargers…).
- The user asks what is near a location or wants places within a radius.
- The user wants an address located (geocoded) on the map.

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
```

Full flag reference and JSON shapes: sub-skill `tasco_jarvis_map:search`.

Answer strictly from the returned JSON — never invent places, addresses,
or coordinates that are not in a result.
