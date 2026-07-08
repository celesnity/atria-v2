# ATRIA.md — Project context for the Atria agent

This file is loaded into the Atria agent's context at runtime (project-root
`ATRIA.md`, merged hierarchically). Keep it short and behavioral.

## Maintenance-knowledge questions → always use the copilot tool

Answer ANY aircraft-maintenance knowledge question (AMM, MEL, CDL, TSM,
engineering orders, defect assessment, dispatch-readiness, reference validation,
ATA-chapter lookups) by calling the `maintenance_copilot_query` tool. It runs
grounded RAG and renders a cited, confidence-scored structured answer card in
the UI. Do not run the copilot CLI (`python copilot.py ...`) for user
questions — that runbook is for human operators and diagnostics only.

- Do NOT answer maintenance questions from your own knowledge.
- Do NOT read, grep, list, or `cat` `modules/*/sample_manuals/` — those files
  are the RAG corpus and are access-protected; going around the tool bypasses
  retrieval, citations, revision-awareness, and guardrails.
- If the tool reports its service unavailable (a `service_unavailable`
  validation warning), tell the user the copilot is down and stop. Never open
  the manuals or answer from memory as a fallback.
- Cite every claim from the returned citations, surface `review_required` and
  low confidence plainly, and remember: advisory only — a licensed engineer
  makes and signs every dispatch decision.
