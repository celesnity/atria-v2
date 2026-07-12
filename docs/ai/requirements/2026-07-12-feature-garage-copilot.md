---
phase: requirements
title: Requirements & Problem Understanding — garage-copilot
description: KTV repair copilot ("vibe repairing") — conversation with the AI is the work log
---

# Requirements & Problem Understanding

Feature: **garage-copilot** · Sources: `garage/PROBLEM.md`, `garage/SKILL.md`, stakeholder Q&A 2026-07-12.

## Problem Statement
**What problem are we solving?**

At the S&S Automotive HCMC Service Centre (Rolls-Royce, Lamborghini, McLaren), the technician's
diagnostic reasoning — the most valuable data in the workshop — is never captured, while the
financial trail (RO → settlement → invoice) is airtight. Consequences (severity from
`garage/PROBLEM.md` §12):

- **Diagnosis ★★★★★**: depends on individual experience; when the senior technician is busy,
  everyone waits. Typically the longest stage of a job (~2h vs ~1.5h hands-on repair).
- **Knowledge search ★★★★★**: answers live in people, PDFs, Facebook, Zalo, YouTube, OEM portals;
  finding one can take longer than the repair itself.
- **Knowledge loss ★★★★★**: every closed RO discards the diagnostic reasoning; when a senior
  mechanic leaves, years of experience leave with them.
- **Documentation ★★★**: recorded manually after the work, when details are easiest to forget.
- **Re-entry ★★★★ (12.9)**: the same information is touched five or six times by different people.

Affected: Technicians (KTV) primarily; Service Advisors, Service Managers, and future technicians
downstream. Current workaround: ask the senior, search chat groups and manuals ad hoc, fill Excel
reports by hand at end of day.

## Goals & Objectives
**What do we want to achieve?**

Core concept — **"vibe repairing"**: like a developer pair-programming with Claude Code, the KTV
pairs with an AI copilot while repairing the car. The conversation itself becomes the work log and
the workshop's organizational memory.

Primary goals (v1):
1. A KTV can converse with the copilot (text, Atria web UI) to diagnose and fix a vehicle faster,
   instead of waiting on the senior technician or hunting through scattered sources.
2. Every session is anchored to an **RO + VIN** — no RO, no repair session (mirrors the workshop's
   RO-first control regime and makes the log a compliance asset, not a liability).
3. Answers are grounded: manual-based guidance is cited; general LLM knowledge is visibly labeled
   as an unverified suggestion.
4. On session close, the system produces a **structured work-log record** (see User Stories) on top
   of the raw transcript. Log language: Vietnamese narrative with English technical terms kept
   verbatim; the reported-symptom field is always verbatim as spoken.
5. Past work logs are **searchable** ("has anyone seen vibration at 60 km/h on a Ghost?") and feed
   back into the copilot's answers — the knowledge flywheel.

Secondary goals:
- Vietnamese-first conversation with natural English code-switching ("thay cái CV axle");
  internal VI→EN translation for retrieval; citations stay in manual language.
- The structured log is readable by managers/SAs so ops artifacts can later be derived from it.

Non-goals (v1):
- **No voice interface** (demo is text in Atria web UI; voice is the likely v2 priority).
- **No SAP writes**, no auto-filled daily Excel reports, no invoice text generation (read-only
  drafts at most, later).
- **No bypass of compliance gates**: the copilot replaces the *knowledge* wait (senior / manuals /
  other dealers), never SM approvals or the supplementary-estimate (Dự Toán Phát Sinh) flow. Those
  stay human; the copilot may at most help draft a request.
- No customer-facing or SA-facing features.
- No real OEM manual licensing work (demo corpus only).

## User Stories & Use Cases
**How will users interact with the solution?**

- As a **KTV**, I want to start a copilot session by entering the RO number and VIN, so that my
  work conversation is anchored to an authorized job (and refused without one).
- As a **KTV**, I want to describe the symptom in Vietnamese exactly as the customer said it
  ("xe chạy khoảng 60km/h thì rung"), so that no fidelity is lost to translation through the SA.
- As a **KTV**, I want the copilot to ask clarifying questions and propose ranked hypotheses with
  manual citations, so that I converge on the root cause faster than waiting for the senior.
- As a **KTV**, I want manual-grounded steps clearly distinguished from the model's general
  suggestions, so that I never apply an uncited procedure to a Rolls-Royce.
- As a **KTV**, I want my conversation to *be* my documentation — when I close the session, a
  structured work log is generated (reported symptom verbatim, hypotheses tried incl. dead ends,
  diagnostic steps, root cause, fix applied, parts used, tools used, elapsed time) with the raw
  transcript preserved underneath.
- As a **KTV (later, or another KTV)**, I want to search past sessions by symptom/vehicle, so that
  a problem solved once is never re-diagnosed from scratch.
- As a **Service Manager**, I want to read the structured work log per RO, so that I see what was
  actually done without deciphering a raw chat transcript.

Edge cases to consider:
- Session start without RO/VIN → copilot refuses to enter repair mode (polite, explains the rule).
- RAG returns nothing relevant → copilot says so and clearly labels any fallback suggestion.
- Mixed-language queries and English part names inside Vietnamese sentences.
- Session abandoned mid-repair (no close) → log generated with status `incomplete`.
- Multiple sessions against the same RO (multi-day repairs) → logs linked by RO.

## Success Criteria
**How will we know when we're done?**

Success bar (chosen): **end-to-end scenario demo** in Atria's web UI. The demo scenario:

1. KTV opens a session against a (mock) RO + VIN.
2. Describes "xe chạy khoảng 60km/h thì rung" in Vietnamese.
3. Copilot asks clarifying questions, retrieves cited manual guidance, hypotheses are worked
   through (wheel balancing considered and rejected), converging on damaged CV axle.
4. Session closes → structured work-log record is produced and viewable.
5. A later search for the same symptom finds the session and its resolution.

Acceptance criteria:
- Every factual repair instruction shown is either cited to the manual corpus or explicitly labeled
  "not from manuals — general suggestion, verify before applying."
- Session cannot enter repair mode without RO + VIN.
- The generated work log contains all schema fields (see design doc) with content faithful to the
  transcript.
- Search over past logs returns the demo session for a paraphrased symptom query.
- Stakeholders watching say "I want this in the workshop."

## Constraints & Assumptions
**What limitations do we need to work within?**

Technical constraints:
- Build inside **Atria** (this repo): FastAPI + React web UI, ReAct agent, tool registry, session
  persistence, PromptComposer.
- Reuse the **enterprise_knowledge module's retrieval stack** (hybrid dense+BM25 via Qdrant,
  chunking, synthesis, guardrails, audit — already produces cited Vietnamese answers).
  [Implementation finding 2026-07-12: the originally-planned maintenance_copilot pipeline was
  deleted from the repo (commits 3950a51, 6889b8b) and its service moved to the cloud;
  enterprise_knowledge is its in-repo transformation and a strictly better fit.]
- garage-copilot is built as a **code-bearing skill module** (`modules/garage_copilot/`, SKILL.md
  `tools:` frontmatter) — the sanctioned module pattern in the current codebase.
- Infra: **Qdrant** must be running locally for index/retrieval (alongside the existing
  docker db/redis services).
- Atria agent-design rules apply: no hard-coded if/else conversation flow (the LLM decides each
  turn); no tables in system prompts.

Business constraints:
- Luxury brands: a hallucinated torque spec is an expensive mistake → labeling/citation discipline
  is a hard requirement, not polish.
- The RO-first control regime is non-negotiable; the copilot must reinforce it.

Assumptions (named and accepted):
- Demo uses a sample automotive manual corpus, not licensed OEM manuals.
- RO + VIN are entered manually at session start (no SAP lookup); mock RO data is acceptable.
- Manager-visibility / surveillance policy for logs is deferred to the pilot phase.
- Demo audience is internal stakeholders; no production hardening (auth, multi-tenant) in v1.
- Technician identity is a free-text name entered at session start (no user accounts in v1).
- "Session close" is an explicit close action in the web UI; abandoned sessions are swept into an
  `incomplete` work log.
- `elapsed_time` in the work log is session duration, NOT labor time — it must not be used for
  billable-hours or KTV-efficiency reporting (the KTV may chat while doing unrelated work).

## Questions & Open Items
**What do we still need to clarify?**

Resolved during requirements review (2026-07-12):
- **Demo corpus** → author sample workshop-manual excerpts mirroring
  `modules/maintenance_copilot/sample_manuals/` structure, deliberately deep on the demo scenario
  domain (driveline vibration, CV axle, wheel balancing). Zero licensing risk; corpus guaranteed
  to support the demo script. (Stakeholder decision.)
- **Work-log language** → Vietnamese narrative with English technical terms verbatim; symptom
  field always verbatim as spoken. (Stakeholder decision.)
- **Work-log storage** → extend Atria session storage under `ATRIA_DIR` (design decision D4).
- **VI→EN retrieval quality** → validated by an integration test before the demo; fallback is
  bilingual query expansion inside the tool (design decision D5).

Still open / deferred to v2+:
- Voice modality, ops report drafts, SA/manager surfaces, SAP integration, photo evidence
  attachments.
- Manager-visibility / surveillance policy for logs (pilot-phase decision).
