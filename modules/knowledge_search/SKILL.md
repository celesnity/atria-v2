---
name: knowledge_search
description: Generic hybrid search over registered knowledge sources (enterprise documents, map places, ...). Use the knowledge_search tool whenever the user asks a question answerable from indexed domain data.
tools: tools.py
---

# knowledge_search

One tool, many sources. Call `knowledge_search(query, source, filters?, limit?)`.

- Pick `source` from the enum by intent: company policies/procedures ->
  `documents`; places, venues, addresses, POIs -> `places`.
- Write `query` in the user's language (Vietnamese queries work best for the
  Vietnamese corpora). Put hard constraints in `filters`, soft preferences in
  the query text.
- Read `facets` in the result to discover valid filter values and refine.
- A small `top_margin` (< 0.2) with several distinct candidates means the
  match is ambiguous: ask the user a clarifying question instead of guessing.
- Results are already permission-filtered for the acting user. If `hits` is
  empty with a `note` about access, tell the user no accessible information
  was found — do not try to bypass it.
