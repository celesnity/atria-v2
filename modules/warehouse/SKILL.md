---
name: warehouse
description: Warehouse / inventory management backed by SQLite — items, stock movements, sales with undo, low-stock signals, reporting, a GearStock dashboard, and a chat item-form block.
---

# warehouse

Warehouse / inventory management backed by a single embedded **SQLite** database
(`data/warehouse.db`). Stock lives in an `items` table and every change is
recorded in an append-only `movements` audit ledger. Also ships a UI block that
pushes a pre-filled item form into the chat.

## When to use

- The user asks to add, update, remove, or list warehouse stock.
- The user wants stock movements: receive, ship, adjust, or relocate items.
- The user asks for reports: summary KPIs, low-stock, valuation, or history.
- The user wants to "fill the form" / "open the item form" for a SKU.
- The user wants to export, import, or back up inventory data.

## Data model

SQLite DB at `<modules>/warehouse/data/warehouse.db`, created automatically on
first use (seeded from sample data, or migrated from a legacy `inventory.csv`
if present). Two tables:

- `items` — current state, one row per SKU: `sku` (primary key), `name`,
  `name_vi` (Vietnamese display name), `category`, `location`, `quantity`
  (int), `unit_price` (float, VND by convention), `reorder_level` (int),
  `ordered_by`/`ordered_at` (restock-ordered marker, cleared by `receive`),
  `created_at`, `updated_at` (ISO-8601 UTC). Schema v2 — older DBs are
  migrated in place on first connect.
- `movements` — append-only audit ledger: `sku`, `kind`, `delta`, `balance`,
  `reason`, `reference`, `created_at`. Every stock change logs a movement in the
  same transaction, so the ledger never drifts from `items`.

The DB path can be overridden with `ATRIA_WAREHOUSE_DB` (used by tests). The
live DB file is gitignored. An item is **low stock** when
`quantity <= reorder_level`.

## How to use

Bash CWD is the chat workspace, not the modules root. Use absolute paths.
Replace `<modules>` with the absolute modules root announced in the "Active
Modules" prompt section. All operations are subcommands of
`scripts/inventory.py`.

Most common — list current stock (add `--json` for machine-readable output):

```
python <modules>/warehouse/scripts/inventory.py list
python <modules>/warehouse/scripts/inventory.py list --query widget
```

## Sub-skills (load on demand)

For anything beyond a basic `list`, load the matching sub-skill with
`invoke_skill` — do not guess flags:

- `invoke_skill("warehouse:reporting")` — filtered listing, `summary`,
  `low-stock`, `valuation`, `history`, `snapshot` (the dashboard payload), and
  the read-only `query` command.
- `invoke_skill("warehouse:stock-ops")` — `add`, `update`, `remove`, plus stock
  movements: `receive`, `ship`, `sell` (multi-line, undoable via `revert`),
  `adjust`, `move`, `set-reorder`, `mark-ordered`/`unmark-ordered`.
- `invoke_skill("warehouse:data-io")` — `export`, `import` (incl. stdin),
  `migrate`, `reset`.

## Item form block

Push the item-form block into the chat. With no `--sku`, opens an empty form for
creating a new item. With `--sku`, pre-fills from the current DB row:

```
python <modules>/warehouse/scripts/push_form.py
python <modules>/warehouse/scripts/push_form.py --sku SKU-001
```

When the user clicks Save, the block does NOT call back through a typed RPC.
Instead it injects a plain chat message naming the exact
`inventory.py add|update --sku ... --name ...` command to run. Treat that
injected message like any other user prompt: parse it, run the suggested
command, and confirm the result. Clicking Cancel injects a short "no changes to
apply" message.

`push_form.py` reads the DB before pushing and injects autocomplete suggestions
(distinct `sku`, `name`, `location` values) for a native `<datalist>` dropdown,
and blocks duplicate SKUs client-side in create mode. It reads
`$ATRIA_SESSION_ID` and `$ATRIA_API_BASE` from the bash env (both exported
automatically) — do not set them manually.

## Files

- `SKILL.md` — this overview.
- `skills/*.md` — on-demand sub-skill guides (reporting, stock-ops, data-io).
- `scripts/_db.py` — SQLite connection, schema bootstrap/migration, seeding.
- `scripts/inventory.py` — inventory CLI (state, CRUD, stock ops, sales/undo,
  import/export, dashboard snapshot).
- `scripts/push_form.py` — pushes `blocks/item_form.html` via `push_block`.
- `blocks/item_form.html` — sandboxed iframe form for an inventory item.
- `dashboard.html` — GearStock dashboard (bilingual EN·VI): inventory, record
  sale (POS cart), needs-restock and sales-history tabs plus a CSV import
  wizard, all driven by `inventory.py` through the AtriaDash bridge. Includes
  **Minder**, a docked chat assistant: typed questions are answered by the
  REAL main-chat agent (via `scripts/minder_chat.py` → the backend's
  `/api/modules/warehouse/chat` route, one dedicated auto-titled session per
  widget conversation, visible in chat history), while the four data
  quick-chips answer instantly from the local snapshot with charts. If the
  agent is unreachable the widget falls back to a local keyword brain
  (replies marked "· offline"). The warehouse chat runs with **thinking off**,
  starts **on the warehouse module directory** (its bash cwd holds
  `scripts/inventory.py` + `data/warehouse.db`), and gets the **live snapshot
  injected into every turn** so it answers from data (not filesystem
  exploration) even with a weak model; replies match the user's language.
  Asking for a "report"/"file"/"export" deterministically writes a markdown
  report (`inventory.py report`) into the conversation's working dir — it shows
  in that conversation's Files tab and the reply names it truthfully. Minder
  **cannot generate images** and says so instead of pretending. The save button
  moves the conversation into the module's "Warehouse" workspace project
  (created after in-chat confirmation via `/chat/save`), re-titles it by
  LLM-summarizing the recent messages, and opens it in the main history via the
  dashboard bridge's `openHistory`.
- `scripts/minder_chat.py` — loopback client for the Minder widget (stdin
  JSON → POST `$ATRIA_API_BASE/api/modules/warehouse/chat` → stdout JSON).
- `data/warehouse.db` — live SQLite store (auto-created; gitignored).
