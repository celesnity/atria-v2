# Minder Optimize — Guided · Implementation Brief

For the coding agent building the production version of **`Minder Optimize - Guided.dc.html`**. This describes what the design is, how it behaves, and the rules that must hold. The prototype is the source of truth for layout and copy; this brief explains the intent so you don't reverse-engineer it.

---

## 1. What this screen is

A **guided operational-decision experience** for a first-time shift manager. When a production line is predicted to miss its shift target, Minder opens a *decision case*, recommends one action, and walks the manager through approving and validating it. The whole product is built on **progressive disclosure** — a new user should understand what to do in under 60 seconds, and only dig into detail on demand.

It is NOT a dashboard. Monitoring is secondary; the recommended decision is the hero.

Persona: **Shift Manager** (approves). Secondary: CI Engineer (read-only).

Design language: **Celesnity / Minder** — dark-first, near-black bg, single indigo accent (`#4A6CF7` + highlight `#7B8FFF`), Be Vietnam Pro (sans) / Newsreader italic (the one "hinge" word in a headline) / JetBrains Mono (eyebrows, IDs). Sentence case. No emoji. Red reserved for urgent/unsafe/blocked/failed only. Generous whitespace, few nested borders, large body text (16px base).

---

## 2. Navigation — exactly 4 items

`Today · Decisions · Performance · History` (top bar). Do not add more. The earlier architecture's extra sections fold in: Investigations → inside Decisions; Experiments → History ▸ Improvement; Data & KPI Governance → Admin/Settings; Audit → History details.

---

## 3. Progressive disclosure — the core rule

Three levels. Each deeper level is opt-in and must not be visible until the user asks for it.

- **Level 1 — Default.** What needs attention, what Minder recommends, the expected result, the risk, and ONE primary action. Nothing else.
- **Level 2 — Explanation.** Opened by the "How did Minder reach this?" pill. Five plain-language questions, in this order:
  1. What is happening?
  2. Why is it happening?
  3. What happens if we do nothing?
  4. What options were considered? (the alternatives list, recommended one marked, blocked one in red)
  5. Why is this recommended?
- **Level 3 — Evidence & audit.** Opened by "See the data behind this →" (and "Request more evidence" in the review drawer). A right-hand drawer: source events (value, source module, freshness, muted event ID), conflicts in red, then **collapsed** `<details>` disclosures for formulas/model versions and the full decision object JSON.

Hard visual limits (keep these): ≤4 nav items, ≤3 metrics above the fold, **one** primary CTA per screen, **one** chart on the default decision screen, event IDs/formulas/model versions hidden by default, minimal uppercase.

---

## 4. Screens & states

### Today
Human greeting that names the problem in one line ("Good morning. Line 2 needs your *attention.*" + one-sentence consequence). An attention summary of 3 plain stats (Needs your decision: 1 · Actions in progress: 2 · Improvements confirmed today: +71). Then ONE primary case card (plain-language situation + recommendation + `expected recovery · risk · time-to-decide`), primary CTA **"Review recommendation"** → goes to the Decision screen.

### Decision — three sub-states driven by `status`
- **`awaiting`** (Level 1 + optional Level 2): eyebrow, one-sentence situation, exactly 3 metrics (units short / chance of reaching target / minutes to decide), one forecast chart (with-action vs no-action vs target), the recommendation card (indigo hinge word on the pallet ID), 3 recommendation metrics (expected recovery / risk / confidence), primary CTA **"Review and send to Move"**, quiet pill **"How did Minder reach this?"**. The How panel and evidence drawer hang off this state.
- **`executing`**: humanized status block — "Move accepted the request." + task ID, forklift assigned, expected arrival, next check time. Technical payload (command, idempotency key, correlation ID, owning module) lives inside a collapsed "Technical details".
- **`completed`**: "The action worked." + expected-vs-measured bars (75 vs 71) + "Result confirmed — within the expected range" + no-side-effects line + collapsed technical details (baseline/comparison window, method, write-back).

### Performance
Quiet supporting view — a KPI row + a single output-vs-target trend. Explicitly says Minder only opens a decision when a human is needed. Do not turn this into a dense monitor.

### History
Sub-tabs **Decisions** (list: title, time, actor, outcome status — Worked / Rejected / Inconclusive / Executing, color-coded) and **Improvement** (experiments Minder is testing/confirming). Rows open the decision case.

### Review drawer (approval)
Right-hand drawer opened by the primary CTA. Sections in order: What will happen · Expected result · Safety and constraints (green when passed) · Owning module · Stop/rollback condition. **One** prominent button **"Approve and send"**. Modify / Request more evidence / Defer / Reject are a **secondary, lower-weight** action row — never equal visual weight to Approve. Footer note: actor, role, time, reason are recorded.

---

## 5. Interaction / state model

Single state machine:
- `status`: `awaiting → executing → completed`. **Approve and send** sets `executing`, then (real system: on Move acknowledgement) `completed`. In the prototype this is a timer; in production it's the connector callback.
- `howOpen`, `reviewOpen`, `evidenceOpen`: booleans for the disclosure levels/drawers. Only one drawer open at a time; opening evidence closes review.
- The top **"Prototype states"** bar (Today overview / Decision summary / How / Review & approve / Executed & validated) is **DEMO SCAFFOLDING ONLY** — it teleports between the five states for review/screenshotting. **Remove it (or gate it behind a debug flag) in production.** Real users reach those states through the natural flow.
- The **"Simulation"** banner is a genuine product element — it must stay whenever the app is running on simulated Produce/Move data, and disappear when connected to live sources.

---

## 6. Humanized language map (enforce in copy)

Decision Trace → **How Minder reached this** · Observed → **Live data** · Calculated → **Calculated from live data** · Inferred → **Likely explanation** · Predicted → **Expected outcome** · Validated → **Result confirmed** · Attainment probability → **Chance of reaching target** · Execute → **Send action** / "Send to Move" · Provenance → **Data sources**. Keep the module boundary explicit and reassuring: "Minder asks Move to do it; Minder does not control the forklift or machine directly."

---

## 7. Where real integration replaces the mock

Everything is simulated today. Wire these:
- **Forecast / recommendation / alternatives / constraints** — currently hardcoded scenario values. Back with the forecast model, ranking model, and the Protect rule engine (the blocked "+8% speed" option must come from a real hard-constraint check on machine health, not a canned flag).
- **Evidence items** — currently a static list. Back with the governed data feed; each value keeps source module, event ID, freshness, and conflict info for the Level 3 drawer.
- **Approve → execute** — replace the timer with a real dispatch to the Move connector + acknowledgement callback that advances `status` and fills the task/receipt ID.
- **Validation** — replace fixed 71-vs-75 with the measured pre/post benefit written back to the decision object.
- **`who` / role** — drive Approve availability from the real signed-in role (Shift Manager can approve; CI Engineer is read-only).

---

## 8. Build notes

Single streaming Design Component; all charts are measured-width SVGs (ResizeObserver → forceUpdate) drawn in the logic class. Charts fill container width at fixed height. Inline styles only per the DC model; the `<helmet>` `<style>` block holds media queries, keyframes, and the drawer/animation rules that can't be inline. Loads the Celesnity bundle + tokens. Responsive down to ~360px (nav condenses, single column). Tweak props today: `startScreen`, `demoState` — the latter maps to the demo scaffolding and should not ship.
