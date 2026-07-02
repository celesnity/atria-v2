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

## How to use

Run the CLI via the bash tool (``<modules>`` resolves to the active modules
directory — see the SKILL block header in the system prompt):

- Health check: `python <modules>/data_copilot/scripts/copilot.py health`
- Profile a dataset:
  `python <modules>/data_copilot/scripts/copilot.py profile path/to/data.csv`
- Analyze:
  `python <modules>/data_copilot/scripts/copilot.py analyze path/to/data.csv "What is total revenue by region?"`
  Flags: `--max-repair` (default 3), `--max-verify` (default 2), `--out <dir>`.
- Recent audit events:
  `python <modules>/data_copilot/scripts/copilot.py audit --limit 20`

Configure the model via `DC_<ROLE>_*` env vars (roles: `codegen`, `verify`,
`report`). Defaults target OpenAI with `OPENAI_API_KEY`; point
`DC_CODEGEN_BASE_URL`/`_MODEL`/`_API_KEY` at a local vLLM/Ollama endpoint to run
offline.

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
