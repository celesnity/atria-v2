---
name: vetc_copilot
description: Use for VETC vehicle-ownership tasks (đăng kiểm/insurance/registration deadlines, document wallet, service recommendations, one-tap renewal). Runs via autopilot.py — do not answer regulatory questions from your own knowledge.
---

# vetc_copilot

**VETC Auto-Pilot — P5 demo: AI Vehicle Ownership & Document Assistant.**

Detects a car's legal deadlines, answers ownership questions grounded in the
provided knowledge base, recommends relevant VETC services, and executes a
one-tap renewal against mock APIs (wallet → insurer → document wallet).

## When to use
Vehicle ownership tasks for a VETC user: upcoming đăng kiểm / TNDS insurance /
registration deadlines, "what documents do I need", service recommendations,
and simulated renewals.

## Runbook
All commands run from `modules/vetc_copilot/scripts/` as
`python autopilot.py <command>` (add `--today YYYY-MM-DD` for a fixed demo date):

- Deadlines for a user — `radar --user U001`.
- Answer an ownership question — `ask "<câu hỏi>" --user U001` (grounded + cited).
- Recommend services — `recommend --user U001`.
- Execute a renewal — `renew --user U001 --vehicle VEH001 --service SVC001`.
- Show the document wallet — `wallet --vehicle VEH001`.
- Run the 15 evaluation scenarios — `eval`.
- Launch the demo dashboard — `serve --port 8770` then open `http://localhost:8770`.
- Show the audit trail — `audit --limit 10`.

## Guardrails (non-negotiable)
- **Cite or abstain** — regulatory answers cite a knowledge id; if not covered, say so.
- **Advisory only** — never a binding legal/financial ruling.
- **Consent + privacy** — renewals need explicit consent; never expose another user's data.
- **Simulated** — every renewal/payment is a mock; the real VETC gateway is the production path.
- **Motorbikes** — never show a đăng kiểm deadline for a motorbike.

## Status
Demo (Build Week). Primary target P5; P2 cross-sell/engagement shown on P5 data.
Payments/renewals use mock APIs; the real OAuth2 + payment gateway (VETC SDK) is
the production path.
