---
name: knowledge_search
description: Generic hybrid search over registered knowledge sources (enterprise documents, map places, ...). Use the knowledge_search tool whenever the user asks a question answerable from indexed domain data.
tools: tools.py
---

# knowledge_search

One tool, many sources. Call `knowledge_search(query, source, filters?, limit?)`.

This tool is the ONLY valid source for the domains it indexes. For any
question about company policies, procedures, HR, finance, internal documents,
or about places, venues and POIs: call this tool FIRST and ground your answer
in its results. Never answer such questions from general knowledge, and never
substitute repository files, code search, or shell commands for it — content
found elsewhere is not the organization's knowledge base.

- Pick `source` from the enum by intent: company policies/procedures ->
  `documents`; places, venues, addresses, POIs -> `places`.
- Write `query` in the user's language (Vietnamese queries work best for the
  Vietnamese corpora). Put hard constraints in `filters`, soft preferences in
  the query text.
- Read `facets` in the result to discover valid filter values and refine.
- Quote facts (numbers, durations, amounts, names) exactly as they appear in
  the returned snippets; if the snippet does not contain the fact, say the
  document does not state it rather than filling it in yourself.
- A small `top_margin` (< 0.2) with several distinct candidates means the
  match is ambiguous: ask the user a clarifying question instead of guessing.
- Results are permission-filtered for the acting user, and access control is
  part of the product: if the result `note` says matching documents were
  withheld, tell the user they do not have permission to access that
  information and stop — do not answer from any other source. If `hits` is
  empty with no withheld note, say the information was not found.
