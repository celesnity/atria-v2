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
subagent for it.** Do not spawn a Task/Agent/subagent to run `run`/`resume`, to
draw or send charts, or to call `send_image`/`send_table`/`send_editable_table`.
These UI-callback tools only reach the chat from the main agent loop; a spawned
subagent cannot render them and will drop the visuals. Call the CLI and the
`send_*` tools yourself, directly, in this conversation.

**Never hand-roll the analysis.** For any dataset question — including clustering,
segmentation, and personas — run the `run`/`resume` CLI below. Do NOT write your
own ad-hoc Python script into the workspace and run it with `python`, and do NOT
`pip install` packages (scikit-learn, etc.): the runtime venv has no pip/network
and those installs fail. The module's own sandbox already ships pandas, numpy,
scikit-learn, and matplotlib and generates + repairs the code for you. If a run
returns an error, re-run the CLI (the pipeline self-repairs) or surface the error;
never fall back to writing your own analysis script.

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

### Analysis (graph flow with plan review)

No ingest step is required — `run` reads CSV/Excel/Parquet from any absolute
path. The analysis is a LangGraph loop that pauses once for a human-in-the-loop
plan review before it executes any code, then resumes on your relay of the
user's reply. Repeat the review round-trip as many times as the user keeps
asking for changes.

1. `python <modules>/data_copilot/scripts/copilot.py run "<dataset path>" "<question>" [--domain telecom] [--k N]`
   The dataset and question are both **positional** (no `--dataset`/`--question`
   flags) and the **question is required**. `--domain telecom` tightens
   anti-hallucination rules for FTEL/telecom-churn datasets; `--k` pins a
   cluster count when the request is a segmentation ask. This prints:
   `{"status": "awaiting_review", "thread_id": "...", "plan": "..."}`.
   (`profile "<path>"` gives a quick schema/stats look without an LLM call, if
   you need one before or instead of a full run.)
2. **Show the `plan` field to the user verbatim** and ask them to approve it or
   describe changes. Do not skip this — the graph will not execute any code
   until it is resumed.
3. On the user's reply, relay it as feedback:
   `python <modules>/data_copilot/scripts/copilot.py resume --thread <thread_id> --feedback "<their reply>"`
   - If they approved (or the feedback reads as approval), this prints the
     final `{"status": "done", "thread_id": "...", "dataset": "...", "question": "...", "run_dir": "runs/run-...", "report": "...", "verdict": {...}, "figures": [...]}`.
   - If they asked for changes, this prints another
     `{"status": "awaiting_review", "thread_id": "...", "plan": "..."}` — go back
     to step 2 with the new plan and the same `thread_id`.
4. **Present the final result — and always push the visuals to the chat.** Show
   the `report` field to the user as the answer. Inspect `verdict`; if it marks
   the result unverified (or the report carries an UNVERIFIED banner), say so
   explicitly and do not present the numbers as settled.

   **Always write a real final message — never just "Done"/"DONE".** After the
   analysis (and after sending any charts), your reply MUST present the
   findings: reproduce or summarize the `report` field, call out the key numbers
   / segments / trends in prose, note anything unverified, and say which charts
   you sent. A bare "Done", "Task completed", or one-line acknowledgement is not
   an acceptable final answer for a data-analysis turn — the user asked a
   question, so answer it with the results. Then, in the **same turn**, without
   asking first: for every file listed in `figures` (matplotlib PNGs saved to
   the run dir), call the `send_image` tool with its absolute path and a short
   caption. This is how the chart the analysis drew reaches the user — do not
   just describe it or print the path; send the image. Also call the
   `send_report` tool with `run_dir` set to the `run_dir` field from the `done`
   result, so the rendered report markdown reaches the chat as a report bubble
   (in addition to — not instead of — summarizing it in your final message).
   `send_image`/`send_report` render only in the web UI; in a plain
   terminal/CLI they return `"UI callback unavailable"` — in that case state
   that visuals need the web UI rather than silently dropping them.

   Run outputs (generated code, figures) and the audit trail are stored
   automatically in the per-session data_copilot folder, not the module
   folder — you do not pass or manage those paths.

If a step returns `{"error": …}`, surface that message to the user and stop —
do not fabricate an answer. Run `health` first if you suspect the LLM endpoint
is misconfigured (it returns `{"codegen": "ok"}` when reachable).

**Only when the user wants to view/edit the raw data first (web UI):** ingest it
into the module, then show an editable grid, then run the analysis against the
ingested copy:
  a. `ingest "<absolute path>"` (optionally `--name <base>`) → read `files[].path`
     (absolute) and `files[].file` (data/-relative). Use these verbatim; the name
     is slugified (`Telecom Churn (1).csv` → `telecom-churn.csv`). Multi-sheet
     Excel yields one entry per sheet — ask which sheet if there is more than one.
  b. Call the `send_editable_table` tool with `module="data_copilot"` and
     `file="<files[].file>"`; edits save back to the CSV in place.
  c. `run "<files[].path>" "<question>"` — or pass the ingested name (with or
     without `.csv`, e.g. `telecom-churn`), which `run`/`profile` also resolve
     against the module's `data/` dir — then follow the plan-review loop above.

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
  absolute path for `profile`/`run`. Excel workbooks yield one CSV per sheet.
  Notes: pass the source file's path (quote it if it has spaces/parentheses,
  e.g. the artifact path `"…/008af448_telecom_churn (1).csv"`); the command works
  from any working directory (it resolves the module's `data/` dir from the
  script location, not the CWD). The stored name is slugified — lower-cased with
  non-alphanumerics collapsed to `-` (so `Telecom Churn (1).csv` becomes
  `telecom-churn.csv`) — so use the returned `file`/`path` values verbatim in
  later `send_editable_table`/`run` calls rather than re-deriving the name.
- Profile a dataset:
  `python <modules>/data_copilot/scripts/copilot.py profile path/to/data.csv`
- Start the analysis graph (stops at the human-review interrupt):
  `python <modules>/data_copilot/scripts/copilot.py run path/to/data.csv "What is total revenue by region?" [--domain telecom] [--k N]`
  Prints `{"status": "awaiting_review", "thread_id": "...", "plan": "..."}`.
  Flags: `--domain`, `--k`, `--out <dir>` (default: a fresh `runs/run-<timestamp>` dir), `--thread <id>` (default: derived from `--out`).
- Resume a run's checkpoint with the human's reply to the plan:
  `python <modules>/data_copilot/scripts/copilot.py resume --thread <thread_id> --feedback "<their reply>"`
  Prints the final `{"status": "done", "thread_id": "...", "dataset": "...", "question": "...", "run_dir": "runs/run-...", "report": "...", "verdict": {...}, "figures": [...]}`
  or another `{"status": "awaiting_review", "thread_id": "...", "plan": "..."}` if the feedback asked for changes.
  On `done`, call `send_report` with the returned `run_dir` to push the rendered report to the web UI chat.
- Recent audit events:
  `python <modules>/data_copilot/scripts/copilot.py audit --limit 20`

## Review / fix the source data in chat (web UI)

After ingesting, you can let the user inspect and correct the raw data before
analysis. Call the `send_editable_table` tool with `module="data_copilot"` and
`file="<the file field from ingest>"` (e.g. `sales.csv`) to render an editable
grid; when the user edits cells or adds/removes rows and clicks Save, the CSV is
rewritten in place. In a chat session the grid binds to the session's copy of the
dataset and saves back through the `/api/data-copilot/write` route, so edits
persist where the analysis reads from. Then run `run` against the ingested `path` so the report
reflects the corrected data (and continue the plan-review loop as usual). Recommended flow for a
user-supplied dataset: **ingest → (optionally) `send_editable_table` for review/fix → `run` the
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
