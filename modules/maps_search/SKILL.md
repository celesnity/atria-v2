---
name: maps_search
description: POI place search data module for the conversational map assistant. Ships the get_user_profile tool; place search itself goes through the knowledge_search tool with source="places".
tools: tools.py
---

# maps_search

- Search places with `knowledge_search(query, source="places", filters={...})`.
- Personalization is agent-driven: call `get_user_profile(user_id)` first when
  a user id is known, then fold `preferences` into the query text and `avoid`
  into your judgement of results. Do not expect the engine to personalize.
- For "near me" requests, resolve the focus point (user's stated location)
  and pass `filters.near = {lat, lon}` plus an appropriate `radius_m`.
- Ambiguous place names (low `top_margin`, several similar candidates in
  different cities): ask the user which one they mean before acting.
