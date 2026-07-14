# Enterprise Knowledge — Graph Visualization in the Module Dashboard

**Date:** 2026-07-06
**Module:** `modules/enterprise_knowledge` (EK)
**Status:** Approved design — ready for implementation planning
**Depends on:** the EK GraphRAG feature (spec `2026-07-06-ek-knowledge-graph-design.md`)
**Author:** Brainstormed with Claude (superpowers:brainstorming)

---

## 1. Summary

Add an **interactive graph view** to the EK module dashboard: a browsable, ACL-scoped
node-link visualization of the knowledge graph, with the current search's retrieved
documents highlighted. It lives in `dashboard.html` as a new **Graph** tab beside the
existing Search panel. All data comes from a new `knowledge.py graph export` command that
emits an ACL-filtered subgraph — with layout positions already computed server-side — so
the sandboxed iframe only ever receives nodes the selected user may see.

Chosen during brainstorming: **Both** (browse the graph *and* highlight the retrieved
subgraph), **interactive explore** (click → detail, hover → highlight, pan/zoom),
**hand-rolled SVG + server-computed layout** (Approach A — no vendored library, no CDN,
offline-safe), delivered **in the module dashboard only** (not the main agent chat).

## 2. Goals / Non-Goals

**Goals**
- Let a user visually explore the enterprise knowledge as a graph, scoped to what their
  selected RBAC identity may access.
- Highlight, within that graph, the documents a query just retrieved — turning a search
  result into an explorable "why this answer" picture.
- Keep the ACL boundary airtight: the browser never receives a node the user can't see.
- Stay offline-safe and dependency-free (no vendored megabytes, no runtime CDN), matching
  the repo's ethos.

**Non-Goals (out of scope)**
- Surfacing the graph into the **main agent chat** (as a SandboxedBlock). Dashboard only.
- A **full graph app**: physics simulation, lazy click-to-expand-more, saved views. The
  export returns one bounded, pre-laid-out subgraph per call.
- A vendored/CDN graph library. If the corpus later grows huge or richer physics is wanted,
  cytoscape.js can be swapped in behind the same export contract — a future decision.
- Editing the graph from the UI (read-only visualization).
- Changing the RBAC model, the retrieval pipeline, or the existing Search panel behavior.

## 3. Decisions (from brainstorming)

- **Purpose:** browse + per-query highlight ("Both").
- **Delivery surface:** the EK module dashboard (`dashboard.html`) only.
- **Node model:** Document-centric. `document` nodes (colored by classification) +
  `department` hub nodes; `tag` and `entity` nodes appear as connectors **when present**
  (i.e. after `graph build --extract` / tag backfill). Edges: `IN_DEPARTMENT`
  (document→department) and `RELATED` (document↔document via a shared tag/entity or a
  `RELATED_TO` path).
- **Interactivity:** interactive explore — click node → detail panel, hover → highlight
  node + neighbors, drag-pan + wheel/±-zoom. Retrieved docs pre-highlighted.
- **Rendering (Approach A):** hand-rolled SVG in `dashboard.html` + ~120 lines of vanilla
  JS; node positions computed server-side in Python (deterministic department-clustered
  layout). Zero new JS dependency.

## 4. Architecture & data flow

```
Graph tab opens (or reload / after a search)
  → MinderDash.json('knowledge.py', ['graph','export','--user',U, '--query', q?], {timeout_ms})
    → knowledge.py _cmd_graph_export
       → graph_store.export_subgraph(acl_params(user), ...)   [Neo4j, ACL-scoped Cypher]
       → (if --query) reuse retrieval to get retrieved_doc_ids
       → graph_view.build_view(nodes, edges, retrieved_doc_ids)  [layout x,y + JSON assembly]
    → JSON { nodes, edges, meta }  (stdout)
  → dashboard renders SVG at server-provided x,y + vanilla-JS interactions
```

The bridge (`MinderDash.json` → `POST /api/modules/{name}/run`, 120 s cap) is the existing,
unchanged transport. The Graph tab is a new consumer of it.

## 5. The `graph export` command

Added to the existing `graph` subparser (alongside `build`/`stats`/`reset`):

```
knowledge.py graph export --user U [--query "<q>"] [--department D] [--k N] [--max-nodes 200]
```

- `--user` (required): the RBAC identity to scope the graph to.
- `--query` (optional): if given, run the existing retrieval (vector + graph expand) and
  mark the retrieved documents `retrieved: true`. This is the browse↔highlight tie-in.
- `--department` (optional): narrow to one department *within* the accessible scope.
- `--k` (default 5): retrieval depth when `--query` is used.
- `--max-nodes` (default 200): safety cap; if exceeded, truncate to the most-connected
  nodes and set `meta.truncated=true` (logged, never silent).

**JSON contract (stdout):**
```json
{
  "nodes": [
    {"id":"DOC001","label":"Sổ tay nhân viên","type":"document",
     "classification":"Public","department":"COMP","x":120.0,"y":88.0,"retrieved":true},
    {"id":"dept:COMP","label":"COMP","type":"department","x":150.0,"y":100.0},
    {"id":"tag:nghi_phep","label":"nghỉ phép","type":"tag","x":..,"y":..},
    {"id":"ent:chinh_sach_nghi_phep","label":"chính sách nghỉ phép","type":"entity","x":..,"y":..}
  ],
  "edges": [
    {"source":"DOC001","target":"dept:COMP","type":"IN_DEPARTMENT"},
    {"source":"DOC001","target":"DOC002","type":"RELATED"}
  ],
  "meta": {"user":{"user_id":"U001","role":"Employee","department":"HR"},
           "node_count":N,"truncated":false,"query":"...","retrieved_doc_ids":["DOC001","DOC002"]}
}
```

**Layout (deterministic, Python, no physics engine):** department hubs placed evenly on an
outer circle; each document placed on a small orbit around its department hub; `tag`/`entity`
connectors placed at the centroid of the documents they connect. Positions are a pure
function of the (sorted) node ids, so repeated exports are stable.

**Never hard-fails:** on a Neo4j/driver error, emit
`{"nodes":[],"edges":[],"meta":{"error":"..."}}` (exit 0) so the tab shows a degraded state
rather than breaking. Consistent with the query-path fallback philosophy.

## 6. The dashboard Graph tab

- **Tab bar** `Search | Graph` (mirrors `maintenance_copilot`'s tabbed dashboard). The
  existing Search panel is unchanged and remains the default tab.
- **Graph tab layout:** toolbar (selected-user chip, reload button, zoom ± controls) + SVG
  canvas + classification legend + a slide-in detail panel.
- **Render:** nodes drawn at the server `x,y`. `document` = circle colored by classification
  (Public/Internal/Confidential map to the mockup's green/blue/amber; `department` = rounded
  rect; `tag`/`entity` = smaller circles). Edges = lines. `retrieved:true` nodes get an
  accent ring; the view centers on them when a query context exists.
- **Interactions (vanilla JS):**
  - Click node → detail panel: label, type, classification, department, list of connected
    nodes, and (for a `document` node) a "search related" action that switches to the
    Search tab with the query prefilled to the document's title (no agent involved).
  - Hover node → highlight it + its neighbors + incident edges, dim the rest.
  - Drag background → pan; wheel or ± buttons → zoom (both via SVG `viewBox`).
- **States:** loading (while export runs); empty ("chưa có đồ thị — chạy `graph build`") at
  0 nodes; error (on `meta.error`); `MinderDash.resize()` to fit height.
- The dashboard **trusts the export** — it never fetches or filters raw graph data itself.

## 7. ACL & security (the crux)

**The sandboxed iframe only ever receives nodes the selected user may see.** All ACL lives
server-side in `graph export`:
- `export_subgraph` runs an ACL-scoped Cypher (reusing the `_ACL_WHERE` fragment) that
  returns only: documents the user may access (Public/Internal → all; Confidential → own
  department; Executive → all; Restricted → executive only), their department nodes, the
  tags connected to permitted documents, the entities mentioned by permitted documents, and
  edges among those permitted nodes.
- **Defence in depth:** every `document` node is re-checked with `acl.can_access` (the same
  predicate as retrieval) before it is emitted; any that slips through is dropped.
- Document **titles** (shown as labels) are only emitted for accessible documents —
  consistent with citations, which already reveal accessible titles. No forbidden title or
  metadata reaches the browser.
- `department`/`tag`/`entity` are non-sensitive connectors; they appear only when linked to
  a permitted document, so they cannot reveal a forbidden document's existence beyond what
  the permitted set already implies.

There is **no client-side ACL to bypass** — the security property holds regardless of the
iframe sandbox, because forbidden data is never sent.

## 8. Module surface (files)

**New**
- `modules/enterprise_knowledge/scripts/graph_view.py` — the deterministic layout
  (department-clustered positions), JSON assembly, and retrieved-doc marking. Isolated from
  `graph_store` so layout/formatting is independently testable.

**Changed**
- `modules/enterprise_knowledge/scripts/graph_store.py` — add
  `export_subgraph(acl: dict, department: str|None, max_nodes: int) -> (nodes, edges)`: an
  ACL-scoped Cypher (reuses `_ACL_WHERE`) returning the permitted subgraph.
- `modules/enterprise_knowledge/scripts/knowledge.py` — add the `graph export` subcommand
  (`_cmd_graph_export`): resolve user → `export_subgraph` → optional retrieval marking →
  `graph_view.build_view` → print JSON; defence-in-depth `acl.can_access` re-check.
- `modules/enterprise_knowledge/dashboard.html` — add the Graph tab: tab bar, SVG render,
  interaction JS (inline, to avoid depending on an extra module-file-serving route), detail
  panel, legend, states.

## 9. Testing & definition of done

**Python unit tests** (pytest, FakeRun for Neo4j, matching the existing EK test style):
- `graph_store.export_subgraph`: the Cypher is ACL-scoped (contains `_ACL_WHERE`, binds the
  user's acl params), returns the expected node/edge shape from a fake result.
- `graph_view`: layout is deterministic (same input → same positions), JSON shape matches
  the contract, `retrieved` marking is applied to exactly the retrieved doc ids, `--max-nodes`
  truncation sets `meta.truncated`.
- **ACL-leakage test (critical), parametrized over permission-matrix corners** (Employee/ENG,
  Employee/HR, Executive/EXEC): even if the store returns forbidden documents, `graph export`
  emits **exactly** the permitted document set — 0 Restricted/other-dept-Confidential for a
  non-executive. Mirrors the retrieval leakage test's adversarial "store returns all" shape.
- `knowledge.py`: `graph export` parser + dispatch; graceful `meta.error` on store failure.

**Live UI smoke** (the dashboard JS can't be meaningfully unit-tested headless): with the
running web UI + Neo4j, open the Graph tab as a non-executive user and verify the graph
renders, click→detail / hover→highlight / pan+zoom work, retrieved docs highlight after a
search, and no forbidden document appears.

**Definition of done:**
1. For every matrix-corner user, `graph export` emits exactly their permitted document set
   (0 forbidden). Adversarial leakage test green.
2. The Graph tab renders the ACL-scoped graph and the three interactions work.
3. A query's retrieved documents are highlighted in the graph.
4. Empty (0 nodes) and error (`meta.error`) states are handled gracefully.
5. Zero new JS dependency; the Search panel is unchanged.

## 10. Risks

- **Sparse graph by default** (documented in the GraphRAG spec): backbone-only builds have
  no `tag`/`entity` nodes, so the first render is documents-linked-by-department only. Not a
  bug — the view handles both states; richer after `graph build --extract` / tag backfill.
- **Label leakage** — mitigated: titles are emitted only for permitted documents; connectors
  only appear via permitted documents. Covered by the leakage test.
- **Large corpus** — the current 40-doc corpus renders trivially; `--max-nodes` caps growth
  and `meta.truncated` surfaces it. A future large corpus is the trigger to reconsider a
  vendored library (Approach B).
- **dashboard.html size** — adding the graph JS inline grows the file; if it becomes
  unwieldy, split the graph JS into a sibling asset served via the module file route. Kept
  inline for v1 to avoid a new serving dependency.

## 11. Future upgrade path (not now)

- Push the same graph into the main agent chat as a SandboxedBlock (needs an agent trigger +
  a `--user` resolution policy).
- Swap the hand-rolled renderer for a vendored cytoscape.js (Approach B) if the corpus grows
  large or physics/lazy-expand is wanted — the `graph export` JSON contract stays the same
  (drop the server `x,y` and let cytoscape lay out).
