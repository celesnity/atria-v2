---
name: produce
description: 'Produce — a standalone Manufacturing Execution System (MES) for the shop floor. Track A is pure human-operated software (work queue, e-SOP with poka-yoke, WIP, downtime/andon, scrap, OEE, changeover, shift handover, exceptions, reports, master data). Track B layers Minder co-work on top: read shop-floor state, subscribe to production events, and propose gated commands + decision packets. Ask it "what is the current shift OEE?", "show open exceptions on line 1", or "draft the end-of-shift handover".'
---

# produce

A Manufacturing Execution System (MES). Operators, team leaders, shift supervisors,
plant managers, and FDE/Admin run the shop floor through it. Track A is a pure,
standalone application; Track B exposes a Minder co-work surface over it.

## When to use

Reach for this when someone asks about live shop-floor state or wants to act on it:
the current shift's OEE and its three losses, a line's WIP / bottlenecks, open
downtime and andon calls, blocked jobs (exceptions), the released SOP for a task,
or the shift handover. Use it to explain why a line is behind, to draft an
end-of-shift handover, or to raise and escalate an exception. A licensed operator or
supervisor stays in the loop for every dispatch decision — never bypass the SOP
poka-yoke or the risk gate.

## Reads (state queries — never gated)

- `read_queue` — an operator's task queue, in priority order.
- `read_wip` — WIP per station for a line (find bottlenecks).
- `read_oee` — the shift's OEE and the three losses vs target.
- `read_downtime` — open downtime events plus the line's reason-code library.
- `read_sop` — the released (approved) SOP and its steps for an operation.
- `read_exceptions` — open and escalated exceptions on a line.
- `read_handover` — the outgoing shift's handover and any carry-forward downtime.

## Commands (gated writes — reversible, carry an assumption ledger)

- `cmd_raise_exception` — create an exception from a detected block and escalate to
  the supervisor. Low risk; reversible (resolve the exception to undo).
- `cmd_draft_handover` — build an auto-summarized end-of-shift handover draft from
  live data. Low risk; reversible (delete the draft).
- `cmd_update_production` — reconcile a production record (count and/or station
  status) from a trusted signal. Low risk; reversible.

## Guidance (surfaced into the UI — the person decides)

- `guide_next_step` — suggest the operator's next SOP step / correct setup.
- `guide_decision_packet` — surface a decision packet for the shift supervisor to
  approve; approving it runs the mapped command through the gate.

## Events (subscribe to production activity)

`job.started`, `job.completed`, `step.confirmed`, `downtime.opened`,
`downtime.closed`, `andon.raised`, `exception.raised`.

## Dashboard

The module's dashboard (`http://localhost:9310/`) has five persona tabs — Operator,
Tổ trưởng (team leader), Quản ca (shift supervisor), Quản lý xưởng (plant manager),
and FDE/Admin — each showing the epic panels relevant to that role.
