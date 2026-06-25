# warehouse

Inventory management for a warehouse: SKUs, stock levels, locations, unit
prices, reorder thresholds, and low-stock signals. CSV-backed CRUD with an
interactive dashboard.

## When to use
- When the user asks about warehouse inventory, stock counts, SKUs, locations,
  prices, restocking, or low-stock / reorder alerts.
- When the user wants to add, update, adjust, or remove inventory items.

## Data
Inventory lives in `<modules>/warehouse/data/inventory.csv` with columns:
`sku, name, location, quantity, unit_price, reorder_level, updated_at`.
`inventory.template.csv` holds the empty header used to reset the dataset.

## How to use
Run the inventory CRUD via the bash tool (`<modules>` resolves to the active
modules directory — see the SKILL block header in the system prompt):
- `python <modules>/warehouse/scripts/inventory.py list [--query <text>] [--json]` — list items (optionally filter by SKU/name; `--json` for programmatic output).
- `python <modules>/warehouse/scripts/inventory.py add --sku <s> --name <n> --location <l> --quantity <int> --unit-price <float> --reorder-level <int>` — add an item.
- `python <modules>/warehouse/scripts/inventory.py update --sku <s> [--name ...] [--location ...] [--quantity ...] [--unit-price ...] [--reorder-level ...]` — patch fields on an item.
- `python <modules>/warehouse/scripts/inventory.py adjust --sku <s> --delta <int>` — add a delta to quantity.
- `python <modules>/warehouse/scripts/inventory.py remove --sku <s>` — delete an item.
- `python <modules>/warehouse/scripts/inventory.py reset` — reset the CSV to the empty template.

The dashboard (`dashboard.html`) lists inventory with KPIs (item count, total
value, low-stock count), a filter box, and an inline add/edit dialog; it calls
`inventory.py` directly via the AtriaDash bridge and refreshes on data changes.

To show the inventory as an interactive, user-editable grid in chat (edit cells,
add/delete rows, Save back to the CSV), use the `send_editable_table` tool with
`module="warehouse"` and `file="inventory.csv"`.

Files: scripts/inventory.py, scripts/push_form.py, dashboard.html, blocks/item_form.html, icon.svg
