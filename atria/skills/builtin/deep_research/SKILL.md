---
name: deep_research
description: Multi-source LLM-driven research pipeline (taxonomy + section synthesis).
tools: tools.py
---

When the user asks for **research**, an **analysis report**, or any broad
topical investigation, call `deep_research(topic=...)`. The tool generates a
MECE taxonomy and PAUSES for user review; once accepted, the background
pipeline streams report sections as they complete. Poll `get_research_status`
for progress. Final report is saved as Markdown.

For simple factual lookups, use `web_search` instead.
