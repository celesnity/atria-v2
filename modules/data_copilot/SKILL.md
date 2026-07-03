---
name: data_copilot
description: Data-analysis copilot — answers a natural-language question about a tabular dataset (CSV/Excel/Parquet) by generating Python, running it in a bounded sandbox, self-repairing on error, semantically verifying the result, and returning a grounded Markdown report with charts. Use for exploratory data analysis, ad-hoc metrics, and quick dataset Q&A.
---

# data_copilot

**Data-analysis copilot.** Given a tabular dataset and a natural-language
question, this module generates Python, runs it in a bounded local sandbox,
repairs execution errors, semantically verifies that the output answers the
question, and returns a grounded Markdown report (with any charts).

The loop is a clean reimplementation of the analysis pipeline from the
`data-agent` project — no self-evolution engine, no external UI.

## When to use

Reach for this module when the user has a dataset (CSV, Excel, or Parquet) and
asks a question that is answered by computing over it — totals, breakdowns,
correlations, trends, quick charts — rather than by reading documentation.

## Runbook — the standard flow

**Run this entire runbook inline, in the current agent turn — never dispatch a
subagent for it.** Do not spawn a Task/Agent/subagent to run `analyze`/`persona`,
to draw or send charts, or to call `send_image`/`send_table`/`send_editable_table`.
These UI-callback tools only reach the chat from the main agent loop; a spawned
subagent cannot render them and will drop the visuals. Call the CLI and the
`send_*` tools yourself, directly, in this conversation.

Follow these steps in order. Every command is a `python
<modules>/data_copilot/scripts/copilot.py <subcommand> …` call run through the
bash tool (`<modules>` resolves to the active modules directory — see the SKILL
block header in the system prompt). Each subcommand prints a single JSON object
to stdout; parse it and act on the fields named below.

1. **Get the dataset's absolute path.** Use the file's full absolute path — for
   an uploaded file that is the artifact path, e.g.
   `"/root/.atria/workspaces/.../conversations/234/008af448_telecom_churn (1).csv"`.
   Always quote paths with spaces or parentheses. Do **not** `cd` into the module
   or pass a path relative to it. Supported inputs: `.csv`, `.xlsx`/`.xls`,
   `.parquet`.

2. **Analyze it directly — no ingest needed.** Run
   `analyze "<absolute path>" "<the user's question in plain language>"`.
   `analyze` and `profile` read CSV/Excel/Parquet from any path, so this is the
   normal path for "just answer my question". The dataset and question are both
   **positional** (no `--dataset`/`--question` flags), and the **question is
   required**. Tune with `--max-repair` / `--max-verify` only if needed.
   (`profile "<path>"` gives a quick schema/stats look without an LLM call.)

3. **Present the result — and always push the visuals to the chat.** Show the
   `report` field to the user as the answer. If `verified` is `false` (or the
   report carries the UNVERIFIED banner), say so explicitly and do not present the
   numbers as settled. Then, in the **same turn**, without asking first:
   - **For every file listed in `figures`** (matplotlib PNGs saved to the run
     dir), call the `send_image` tool with its absolute path and a short caption.
     This is how the chart the analysis drew reaches the user — do not just
     describe it or print the path; send the image.
   - **If the summary has a non-null `result_table`**, call the `send_table` tool
     with `file=<result_table>`, a short `title`, and
     `suggestions=<summary.suggestions>` to render an interactive table + chart in
     the chat. **Forward `summary.suggestions` verbatim** — do not strip fields.
     Each suggestion already carries the chart-drawing fields the web UI needs:
     `chart_type` (`bar`/`line`/`area`/`pie`/`doughnut`/`scatter`/`combo`/`radar`),
     `x`, `y[]`, `title`, `description` (one-line caption), `labels` (series key →
     display name), `units` (series key → unit label such as `%` or `triệu VND`),
     and — for mixed charts — `combo` (series key → `bar`/`line`), `secondaryAxis`
     (series keys on the right-hand y-axis), and `normalized` (radar 0–100). The
     web UI draws bars/lines/combo/radar, a secondary axis, and unit-suffixed
     ticks/tooltips from these fields, so passing them all is what makes the chart
     rich. You may lightly adjust them (e.g. fill in a `units` map or set a
     clearer `title`) but keep the structure intact.
   - **Pivot / cross-tab breakdowns.** When the question compares a measure
     across two dimensions (e.g. "sales by region and category", "revenue per
     month by channel"), `analyze` writes the result table as a **wide pivot**
     — one row per primary category (the first column) and one numeric column
     per value of the secondary dimension. Send it exactly like any other
     result: call `send_table` with `file=<result_table>` and
     `suggestions=<summary.suggestions>`. The heuristics turn that wide pivot
     into a **grouped multi-series chart** automatically — `x` = the first
     column, `y[]` = the pivoted measure columns — so a "region × category"
     pivot renders as grouped bars (with line/radar alternates in the chart's
     type switcher). You do not build the chart yourself; just forward the
     pivot CSV and its suggestions. If `suggestions` is unexpectedly empty for a
     pivot (e.g. the measure columns weren't detected as numeric), add one
     suggestion by hand: `chart_type: "bar"`, `x` = the first column, `y` = the
     remaining numeric columns.
   - **When the user wants to edit the result** (or asked for an editable
     dataframe), use the ingest → `send_editable_table` flow below — a plain
     `analyze` result table is read-only. See "Only when the user wants to
     view/edit the raw data".

   These `send_*` tools render only in the web UI; in a plain terminal/CLI they
   return `"UI callback unavailable"`. In that case, do not silently drop the
   data — state that visuals need the web UI and fall back to showing the
   values inline (e.g. `cat` the `result_table`).

   Ingested datasets, run outputs (code, figures, `result.csv`), and the audit
   trail are stored automatically in the per-session data_copilot folder, not the
   module folder — you do not pass or manage those paths.

**Only when the user wants to view/edit the raw data first (web UI):** ingest it
into the module, then show an editable grid, then analyze the ingested copy:
  a. `ingest "<absolute path>"` (optionally `--name <base>`) → read `files[].path`
     (absolute) and `files[].file` (data/-relative). Use these verbatim; the name
     is slugified (`Telecom Churn (1).csv` → `telecom-churn.csv`). Multi-sheet
     Excel yields one entry per sheet — ask which sheet if there is more than one.
  b. Call the `send_editable_table` tool with `module="data_copilot"` and
     `file="<files[].file>"`; edits save back to the CSV in place.
  c. `analyze "<files[].path>" "<question>"` — or pass the ingested name (with or
     without `.csv`, e.g. `telecom-churn`), which `analyze`/`profile` also resolve
     against the module's `data/` dir.

If a step returns `{"error": …}`, surface that message to the user and stop —
do not fabricate an answer. Run `health` first if you suspect the LLM endpoint
is misconfigured (it returns `{"codegen": "ok"}` when reachable).

## Persona / customer segmentation

When the user asks to **cluster / segment customers or build personas**
("phân cụm", "persona", "segment", "customer groups"), use `persona` instead of
`analyze`:

`python <modules>/data_copilot/scripts/copilot.py persona "<absolute path>" "<the request>" [--domain telecom] [--k N]`

It runs the same generate → run → repair loop, but forces the generated code to
emit a persona array (schema below) which is validated and **written to
`persona.json`** in the run dir, plus a narrative report. Present the `report`
field; if `summary.result_table` is non-null call `send_table` with
`file=<result_table>` and `suggestions=<summary.suggestions>`; mention that
`persona.json` (path in `summary.persona_json`) holds the structured personas.
If `verified` is `false`, say so and do not present the personas as settled.
Add `--domain telecom` only for FTEL/telecom-churn datasets (stricter
anti-hallucination rules). `--k` pins the cluster count when the user asks for a
specific number of segments.

Each persona in `persona.json` has: `cluster_id`, `persona_name`, `support`,
`support_pct`, `confidence`, `priority_score`, `is_anomaly`,
`segmentation_quality`, `risk_tier`, `evidence`, `profile_attributes`,
`recommended_actions`, `sample_persona_text`.

## Commands (reference)

Run the CLI via the bash tool (``<modules>`` resolves to the active modules
directory — see the SKILL block header in the system prompt):

- Health check: `python <modules>/data_copilot/scripts/copilot.py health`
- Ingest a dataset into the module (do this first for any user-supplied file):
  `python <modules>/data_copilot/scripts/copilot.py ingest path/to/data.xlsx`
  Copies/converts a CSV, Excel (.xlsx/.xls), or Parquet file into the module's
  `data/` dir as CSV. Add `--name sales` to control the stored name. It prints
  JSON `{"module": "data_copilot", "files": [{"file": "...", "path": "..."}]}`;
  `file` is the `data/`-relative name for `send_editable_table`, `path` is the
  absolute path for `profile`/`analyze`. Excel workbooks yield one CSV per sheet.
  Notes: pass the source file's path (quote it if it has spaces/parentheses,
  e.g. the artifact path `"…/008af448_telecom_churn (1).csv"`); the command works
  from any working directory (it resolves the module's `data/` dir from the
  script location, not the CWD). The stored name is slugified — lower-cased with
  non-alphanumerics collapsed to `-` (so `Telecom Churn (1).csv` becomes
  `telecom-churn.csv`) — so use the returned `file`/`path` values verbatim in
  later `send_editable_table`/`analyze` calls rather than re-deriving the name.
- Profile a dataset:
  `python <modules>/data_copilot/scripts/copilot.py profile path/to/data.csv`
- Analyze:
  `python <modules>/data_copilot/scripts/copilot.py analyze path/to/data.csv "What is total revenue by region?"`
  Flags: `--max-repair` (default 3), `--max-verify` (default 2), `--out <dir>`.
- Persona clustering (writes persona.json + narrative report):
  `python <modules>/data_copilot/scripts/copilot.py persona path/to/data.csv "Segment customers into personas" [--domain telecom] [--k N]`
  Flags: `--max-repair` (default 3), `--max-verify` (default 2), `--out <dir>`.
- Recent audit events:
  `python <modules>/data_copilot/scripts/copilot.py audit --limit 20`

## Review / fix the source data in chat (web UI)

After ingesting, you can let the user inspect and correct the raw data before
analysis. Call the `send_editable_table` tool with `module="data_copilot"` and
`file="<the file field from ingest>"` (e.g. `sales.csv`) to render an editable
grid; when the user edits cells or adds/removes rows and clicks Save, the CSV is
rewritten in place. In a chat session the grid binds to the session's copy of the
dataset and saves back through the `/api/data-copilot/write` route, so edits
persist where the analysis reads from. Then run `analyze` against the ingested `path` so the report
reflects the corrected data. Recommended flow for a user-supplied dataset:
**ingest → (optionally) `send_editable_table` for review/fix → `analyze` the
ingested path.** This closes the loop so users analyze the data they actually
approved. (Editable tables only render in the web UI.)

## Model configuration

By default the copilot uses the **same LLM as core Atria** — it reads
`ATRIA_MODEL` and `ATRIA_API_BASE_URL` (and `OPENAI_API_KEY`/`OPENROUTER_API_KEY`)
from the environment, so no extra setup is needed. To override per role, set
`DC_<ROLE>_*` env vars (roles: `codegen`, `verify`, `report`) — e.g. point
`DC_CODEGEN_BASE_URL`/`_MODEL`/`_API_KEY` at a local vLLM/Ollama endpoint to run
code generation offline. Resolution order per field: `DC_<ROLE>_*` → `ATRIA_*`
→ OpenAI defaults.

## Guardrails (non-negotiable)

- **Bounded execution.** Generated code runs as a timeout-bounded, output-capped
  subprocess scoped to a run directory. Network access, process spawning, and
  writes outside the run directory are statically blocked before execution.
- **Grounded reports.** The report is grounded in the code's actual printed
  output and produced figures — no invented numbers.
- **No unverified answers presented as settled.** If the repair or verification
  budget is exhausted, the report is labelled UNVERIFIED.
- **Auditable.** Every analysis appends an event (question, dataset, verified,
  retry counts) to the audit trail.
