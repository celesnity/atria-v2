# Current Stage — Tasco Maps Challenge Coverage

_Gap analysis of `tasco_jarvis_map` vs the two Tasco Maps challenge briefs
(Track 1 = Semantic Search & Ranking, Track 2 = Conversational Assistant).
Verified against the code (schema, retrieval/ranking pipeline, chat layer) on
2026-07-10._

Legend: ✅ done · ⚠️ partial · ❌ missing

---

## Challenge 1 — AI Semantic Search & Ranking

| Criterion | Status | Evidence / gap |
|---|---|---|
| Semantic Search (meaning > keywords) | ✅ | Hybrid retrieval fuses lexical + Postgres FTS + **vector cosine**; intent router understands 9 query archetypes |
| Vector Search | ✅ | pgvector exact cosine (`map_embeddings`), query-embedding cache (`map_query_embeddings`) |
| Embeddings | ✅ | `gen_embeddings.py`, OpenAI embeddings, cached |
| Candidate Retrieval | ✅ | `_search_pipeline` in `search_db.py` |
| Relevance Optimization | ✅ | Category precision, sub-city scope filter, brand hard-filter, distance band-trim — all tuned |
| Relevance **score** in output | ✅ | `score` (0–100) + `confidence_score` (0–1) per response |
| Re-ranking | ⚠️ | Fused-score sort + rating tiebreak — a **deterministic** rerank, not a separate learned stage |
| AI Ranking (a **model** ranks) | ⚠️ | Ranking = weighted signal fusion, **not** an ML/learned ranker. LLM only judges in eval, doesn't rank |
| Per-POI **reasons** ("Wi-Fi, quiet, work-friendly") | ❌ | `explain_match` gives a signal breakdown (lex/fts/vec/geo), chat weaves in hours/distance — but **no attribute-based reasons** (data has no attribute fields) |
| Ranking signals: relevance, distance, ratings | ✅ | All three live |
| Ranking signals: **popularity, review insights, freshness, business attributes** | ❌ | **None exist in the schema** — `map_pois` has only name/category/brand/address/geo/rating/hours |

## Challenge 2 — Conversational Map Assistant

| Criterion | Status | Evidence / gap |
|---|---|---|
| Conversational Search | ✅ | Jarvis chat (fast path + ReAct fallback) |
| Multi-turn Interactions | ✅ | Redis `session_context` + slot inheritance (`_merge_prior`) |
| Clarification Questions | ✅ | Ask-which-city when candidates span cities; brand disambiguation |
| Context Understanding | ✅ | Intent + entity extraction, history carry-forward |
| Map Action Generation | ✅ | `map_actions` (pins) + navigation focus target |
| Output: intent + response + confidence | ✅ | `intent`, reply, `confidence_score` all emitted |
| Output: recommendations **with reasons** | ⚠️ | Recommendations yes; reasons only hours/distance in prose, no attribute reasons |
| **Personalized** Recommendations | ❌ | **No User-Preference dataset ingested**, no per-user ranking signal (bench `user_id=1` is nominal) |
| Voice Interaction | ❌ (here) | STT exists on branch `feat/voice-input` but is **not wired into the map dashboard** |

---

## The real gaps, prioritized

1. **POI attribute/amenity data is missing** — biggest gap. No wifi/quiet/parking/price/view/family-friendly fields, so the *flagship* needs-based queries ("quiet coffee shop for work", "coffee shop with parking", "places for children") can't be *confirmed* and can't produce attribute reasons. Track-1 report shows **18/60 eval cases are data-bound on exactly this**. On the data-feasible subset we already pass ~90%.
2. **Personalization** — User-Preference dataset not ingested, doesn't feed ranking. Required for Challenge 2's personalized-recommendation scenario.
3. **Popularity / review / freshness signals** — only relevance + distance + rating are live; the other three named ranking signals have no data source.
4. **AI/learned re-ranker** — ranking is deterministic fusion. Defensible, but if the brief wants a *model* ranking, that's a delta.
5. **Voice** — needs porting from `feat/voice-input` into the map dashboard.
6. **Submission packaging** — `report_track1.md` + the 60-case bench cover methodology and signals well for Track 1, but there's no README in the required submission shape (10 sample queries + setup + models), deck, or video yet.

**Net:** the *retrieval + conversation engine* is largely built and benchmarked (both challenges' architectures exist end-to-end). The remaining gaps are mostly **data-side** (attributes, preferences, popularity/reviews) and **packaging**, not query-understanding.

## Highest-leverage next move

Attribute enrichment (#1) — unlocks both the amenity queries *and* per-POI reasons, which are the two most visible criteria across both briefs.
