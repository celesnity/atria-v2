# optimize_demo · design source

Reference material for `../blocks/guided.html`. **Nothing here is executed** — the repo has no
Design Component runtime, and deliberately so (see below).

| File | What it is |
|---|---|
| `Minder Optimize - Guided.dc.html` | The prototype. Source of truth for **layout and copy**. |
| `GUIDED_DESIGN_BRIEF.md` | The brief. Source of truth for **intent and rules**. |

## Provenance

Both come from the Claude Design project **`73b8309d-b935-460e-816a-12b69de9435b`**
("Fleet Overview Dashboard Spec", owner: Celesnity Command). Snapshot taken **2026-07-16**.

**The Design project is authoritative, not this folder.** These are a point-in-time copy of what
`blocks/guided.html` was ported from — useful for diffing a future redesign against the version we
actually built. If they disagree with the live project, the live project wins. Re-fetch with the
`DesignSync` tool (`method: get_file`, that project ID, the file path above).

## Why the `.dc.html` is not wired up

It is a Claude Design "Design Component": `<x-dc>` + `<helmet>` + `sc-if`/`sc-for`/`{{ }}` bindings +
`class Component extends DCLogic`, with charts drawn via `React.createElement`. Its runtime
(`support.js`) pulls React, ReactDOM and `@babel/standalone` from **unpkg.com**, which fails inside
the module system's sandboxed iframe and offline.

The team already hit this and decided against embedding the runtime — see
`report/PROOF-OF-DONE-optimize-console-v2.md` (lines ~109-115). `Optimize Console V2.dc.html` was
hand-ported to vanilla instead, becoming `../dashboard.html`. `blocks/guided.html` is the same move
for this design.

So the port is by hand, and these files are how you check it stayed faithful.
