# ATRIA.md — Project context for the Atria agent

This file is loaded into the Atria agent's context at runtime (project-root
`ATRIA.md`, merged hierarchically). Keep it short and behavioral.

## Maintenance-knowledge questions → always use the RAG skill

Answer ANY aircraft-maintenance knowledge question (AMM, MEL, CDL, TSM,
engineering orders, defect assessment, dispatch-readiness, reference validation,
ATA-chapter lookups) by invoking the `maintenance_copilot` skill and following
its runbook — run `python copilot.py query "<question in English>" --synthesize`
from `modules/maintenance_copilot/scripts/`.

Do NOT answer from your own knowledge and do NOT read or grep
`modules/maintenance_copilot/sample_manuals/` directly. Those files are the RAG
corpus; reading them bypasses retrieval, citations, revision-awareness, and the
copilot's guardrails. Cite every claim from the returned passages, surface
uncertainty, and remember a licensed engineer signs every dispatch decision —
the copilot is advisory only.
