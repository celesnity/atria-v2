---
name: maintenance_copilot
description: ALWAYS use for ANY aircraft maintenance question (AMM/MEL/CDL/TSM/defect/dispatch/ATA). Prefer the `maintenance_copilot_query` tool — it runs grounded RAG and renders a cited, confidence-scored answer card in the UI. Do NOT grep the manual files or answer from your own knowledge.
tools: tools.py
---

# maintenance_copilot

**AI Maintenance Knowledge Copilot — P1: Concept Brief and Brainstorm.**
Prepared for the Maintenance Control Center (MCC) and Engineering Teams.

Aircraft defect assessment and dispatch decisions still rely heavily on manual
review of dense technical documentation and on individual engineer experience.
As fleets grow and operational tempo increases, that manual approach gets slower
and more error-prone. This module captures how an AI maintenance knowledge
copilot could help: by combining **retrieval-augmented generation (RAG)**,
**document intelligence**, and **knowledge graphs**, it helps MCC and
engineering teams retrieve, validate, and cross-reference maintenance
documentation faster and with fewer errors — while **a licensed engineer stays
in the loop for every dispatch decision. Dispatch is never fully automated.**

## Problem statement

MCC and engineering teams must continuously reference large volumes of
documentation: the Aircraft Maintenance Manual (AMM), Minimum Equipment List
(MEL), Configuration Deviation List (CDL), Troubleshooting Manual (TSM),
engineering orders, and historical defect records. As fleets grow and
operational pressure increases, manual validation becomes more time-consuming
and more susceptible to human error.

Current challenges:

- **Search burden** — engineers spend significant time searching and
  cross-referencing across multiple manuals.
- **Reference errors** — incorrect references to AMM tasks or MEL items may
  lead to delays or operational risk.
- **Manual, inconsistent entry** — defect classifications and dispatch
  conditions are hand-entered and prone to inconsistencies.
- **Fragmented knowledge** — institutional knowledge is spread across
  repositories and historical records with no unified way to query it.
- **Human factors** — fatigue and workload increase the chance of missed
  information, especially during high-pressure AOG (aircraft-on-ground) events.

## When to use

Reach for this module when the user is working aircraft maintenance knowledge
tasks — assessing a defect, finding the right AMM/TSM procedure, validating a
MEL/CDL reference, preparing a dispatch-readiness view, or brainstorming/scoping
the copilot itself. Items below marked **(Pilot)** map directly to the stated
pilot scope; the rest are candidate extensions for later phases.

## Runbook — how to answer a maintenance question

When a user asks a maintenance-knowledge question in natural language, do NOT
answer from your own knowledge. Retrieve from the indexed manuals first, then
answer strictly from what comes back. All commands run from
`modules/maintenance_copilot/scripts/` as `python copilot.py <command>`.

Pick the command that matches the intent:

- **Find a procedure / answer a "how/what/why" question** — run
  `query "<the user's question in English>" --k 5`. To have the copilot compose a
  short answer instead of only listing passages, add `--synthesize`. Restrict to
  a chapter with `--ata 32` when the user names one. Add `--graph` to also pull
  related entities from the knowledge graph.
- **Recommend which references apply to a defect** — run
  `recommend-refs "<defect description>" --k 5`. Returns ranked AMM/MEL/CDL/TSM
  refs with a confidence score each.
- **Check references a user already cited** — run
  `validate '{"defect":"<text>","cited_refs":["MEL 32-31-01", ...]}'`. Each ref
  comes back `pass` (found + supporting citation) or `fail` (not in approved docs).
- **Flag inconsistencies in a defect write-up** — run
  `check '{"defect":"<text>","cited_mel":"MEL 32-40-01","dispatch_condition":"<text>","classification":"C"}'`.
  Surfaces classification/category mismatches and missing-requirement advisories.
- **Explore the knowledge graph** — `graph show <key> --hops 1`; confirm a
  machine-extracted edge with `graph confirm <src> <EDGE_TYPE> <dst>`.
- **Show the audit trail** — `audit --limit 10`.

Translate a non-English question into English for the `query`/`recommend-refs`
text (the corpus is English), but reply to the user in their own language.

How to present every answer (non-negotiable — these mirror the Guardrails below):

- **Cite every claim.** Name the document, revision, and section/chunk from the
  returned `citation` field. Never state anything about AMM/MEL/CDL/TSM content
  without a citation from the retrieved hits.
- **Never decide dispatch.** Present procedures, references, and inconsistencies
  only. Do not say a defect is or is not dispatchable — the licensed engineer
  decides and signs.
- **Surface uncertainty.** If the tool returns `needs_review`, a low confidence,
  a `fail`, or an inconsistency, say so plainly and route it for manual review.
- **Always append the advisory line:** results are advisory only; a licensed
  engineer makes and signs every dispatch decision.

If retrieval returns nothing relevant, say the manuals do not cover it rather
than answering from general knowledge. If a sidecar is down, run `health` and
report which service failed instead of guessing.

## Brainstormed use cases

### Retrieval & search
- **(Pilot)** Natural-language retrieval of relevant maintenance procedures from
  AMM/TSM given a defect description or ATA chapter.
- Voice or free-text query interface for MCC during live AOG events, returning
  the top matching procedure with page/section citation.
- Unified search across AMM, MEL, CDL, TSM, and engineering orders in a single
  query, instead of manual lookups in separate systems.
- Automatic surfacing of the correct manual revision, so engineers never
  reference a superseded AMM/MEL page.

### Validation & cross-referencing
- **(Pilot)** Validate defect entries against approved maintenance documentation
  before submission.
- **(Pilot)** Recommend the relevant AMM, MEL, CDL, or TSM reference for a given
  defect write-up.
- **(Pilot)** Highlight potential inconsistencies (e.g. a dispatch condition that
  doesn't match the cited MEL item) before engineer sign-off.
- Cross-check defect classification against historical similar defects to flag
  unusual or inconsistent categorization.
- Detect missing placarding, tooling, or interval requirements implied by a
  cited MEL/CDL item.

### Decision support
- Dispatch-readiness summary for MCC: open items, applicable MEL/CDL relief, and
  time-limited dispatch deadlines in one view.
- Alerting on approaching MEL category deadlines (A/B/C/D) to prevent lapses.
- Suggested next troubleshooting step from TSM based on reported symptoms and
  prior fix history for the same fault code.
- Fleet-wide pattern detection: recurring defects across tail numbers that may
  indicate a systemic issue.

### Knowledge capture & explainability
- **(Pilot)** Explainable reasoning with source references for every
  recommendation, so engineers can verify rather than blindly trust output.
- Confidence scoring on retrieved references, with low-confidence results routed
  for mandatory manual review.
- Feedback loop where engineer corrections improve future retrieval ranking and
  flag document gaps.
- OCR / digitization of legacy paper logbooks and historical defect records so
  they become searchable.

### Compliance & audit
- Full audit trail linking every AI-suggested reference to the exact document,
  revision, and page used, for regulatory traceability.
- Mandatory human-in-the-loop sign-off: the copilot recommends but a licensed
  engineer always decides and signs.
- Version-aware indexing so retrieval always reflects the currently approved
  AMM/MEL/CDL revision, not a cached or outdated copy.

## Guardrails (non-negotiable)

- **Human-in-the-loop always.** Every recommendation is advisory. A licensed
  engineer makes and signs every dispatch decision. Never phrase output as an
  approval or a final dispatch determination.
- **Always cite sources.** Every reference must name the document, revision, and
  page/section. No unsourced claims about AMM/MEL/CDL/TSM content.
- **Version-aware.** Flag when a cited revision may be superseded; never present
  a cached page as authoritative without a revision marker.
- **Surface uncertainty.** Low-confidence retrievals are labelled and routed for
  mandatory manual review rather than presented as settled.

## Status

P1 — concept brief and brainstorm. Scope definition and use-case prioritization
only; retrieval/indexing implementation (RAG over the actual manuals, knowledge
graph, OCR) belongs to later phases. The `dashboard.html` renders this brief and
the pilot-vs-extension use-case map for review with MCC and engineering.
