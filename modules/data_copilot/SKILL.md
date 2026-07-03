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

Follow these steps in order. Every command is a `python
<modules>/data_copilot/scripts/copilot.py <subcommand> …` call run through the
bash tool (`<modules>` resolves to the active modules directory — see the SKILL
block header in the system prompt). Each subcommand prints a single JSON object
to stdout; parse it and act on the fields named below.

1. **Locate the dataset.** Use the exact path to the user's file. When the user
   uploaded it, that is the artifact path (e.g.
   `".../conversations/234/008af448_telecom_churn (1).csv"`) — always quote
   paths with spaces or parentheses. Supported inputs: `.csv`, `.xlsx`/`.xls`,
   `.parquet`.

2. **Ingest it into the module.** Run `ingest "<source path>"` (optionally
   `--name <base>`). This is required before any editable table and recommended
   before analysis. Read the printed `files[].path` (absolute — use for
   `profile`/`analyze`) and `files[].file` (data/-relative — use for
   `send_editable_table`). Use these returned values verbatim; do not re-derive
   the name (it is slugified, e.g. `Telecom Churn (1).csv` → `telecom-churn.csv`).
   A multi-sheet Excel file returns one entry per sheet — ask the user which
   sheet to analyze if there is more than one.

3. **(Web UI, optional) Let the user review/fix the data.** If the user wants to
   inspect or correct the raw data first, call the `send_editable_table` tool
   with `module="data_copilot"` and `file="<files[].file>"`. Edits are saved back
   to the CSV in place. Skip this if the user just wants an answer.

4. **Analyze.** Run `analyze "<files[].path>" "<the user's question in plain
   language>"`. Phrase the question the way the user asked it. Tune with
   `--max-repair` / `--max-verify` only if needed.

5. **Present the result.** Show the `report` field to the user as the answer. If
   `verified` is `false` (or the report carries the UNVERIFIED banner), say so
   explicitly and do not present the numbers as settled. Mention any files in
   `figures` (charts saved to the run directory).

If a step returns `{"error": …}`, surface that message to the user and stop —
do not fabricate an answer. Run `health` first if you suspect the LLM endpoint
is misconfigured (it returns `{"codegen": "ok"}` when reachable).

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
- Recent audit events:
  `python <modules>/data_copilot/scripts/copilot.py audit --limit 20`

## Review / fix the source data in chat (web UI)

After ingesting, you can let the user inspect and correct the raw data before
analysis. Call the `send_editable_table` tool with `module="data_copilot"` and
`file="<the file field from ingest>"` (e.g. `sales.csv`) to render an editable
grid; when the user edits cells or adds/removes rows and clicks Save, the CSV is
rewritten in place. Then run `analyze` against the ingested `path` so the report
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
