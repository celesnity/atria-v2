# Data Copilot Module — Design Spec

**Date:** 2026-07-02
**Status:** Approved (design); implementation plan pending
**Module path:** `modules/data_copilot/`

## Summary

Integrate the data-analysis capability from the reference project
`.reference/data-agent` (aka "LAMBDA") into atria-v2 as a self-contained
module named `data_copilot`, following the exact conventions established by the
existing `modules/maintenance_copilot`.

The module teaches the atria agent to answer a natural-language question about a
tabular dataset by generating Python, running it in a bounded sandbox,
self-repairing on error, semantically verifying that the output actually answers
the question, and emitting a grounded Markdown report with any charts. Every
step is cited to computed evidence and recorded in an audit trail.

## Scope decisions (locked with user)

1. **Scope = analysis copilot.** Port only the `langgraph_agent` control flow —
   the generate → execute → repair → verify → report loop. Not the thin HTTP
   bridge, not the full app, not a concept-brief-only stub.
2. **Build style = clean reimplementation.** The reference loop's value is its
   *control-flow design*, which is small and clear. Its *code* is welded to
   `torch`, `gradio`, `transformers`, `sentence_transformers`, and the Triadic
   DGM research engine. We reimplement the design using atria's module
   conventions and a lean dependency set, rather than lifting the code.
3. **Sandbox = bounded local subprocess.** No Docker, no Jupyter kernel — atria
   already runs inside a sandbox, so generated code executes as a
   timeout-bounded, output-capped subprocess in a scoped run directory.

## Explicitly out of scope

Left behind in `.reference/data-agent`, not ported:

- Triadic DGM self-evolution (`triadic_dgm/`, `dgm_agent_v2/`, `evolution_dgm/`).
- The Gradio app and React frontend (`ui/`, `ui/deepanalyze_frontend/`).
- The FastAPI service (`api/`).
- Persona-clustering / EDA / metadata scripts (root-level `*.py`, `create_demo_data.py`).
- The Polyglot / benchmark harness (`triadic_dgm/benchmark/`).

## The loop

Distilled from `.reference/data-agent/langgraph_agent/graph.py`:

```
profile dataset
  → generate code
  → guardrail gate (reject dangerous code)
  → execute (sandbox)
      → error?  → repair code → execute        (bounded by --max-repair)
  → verify (does the output answer the question?)
      → REVISE? → regenerate code → execute      (bounded by --max-verify)
  → generate grounded report (+ figures)
  → append audit event
```

Bounds are hard caps. When repair or verify budgets are exhausted, the loop
stops and the report states that the result is unverified / the code still
errors — it never silently presents an unverified answer as settled.

## Components

Each script is a focused, independently testable unit under
`modules/data_copilot/scripts/`, mirroring `maintenance_copilot/scripts/`.

- **`config.py`** — Module-local model-provider config. Maps three feature
  *roles* to OpenAI-compatible endpoints, read from `DC_<ROLE>_<FIELD>` env vars
  with defaults. Roles: `codegen`, `verify`, `report`. Deliberately
  self-contained; does not touch atria's global provider system.
  - **Default endpoint:** OpenAI-compatible at `https://api.openai.com/v1` with
    `OPENAI_API_KEY`, because code generation needs a capable model. Every field
    is overridable via env (e.g. point `DC_CODEGEN_BASE_URL` at a local
    vLLM/Ollama endpoint), exactly like maintenance_copilot's `MC_*` scheme.
- **`client.py`** — `RoleClient`: resolves `chat(role, messages, **kw)` to the
  endpoint configured for that role, reusing one underlying `openai.OpenAI` per
  distinct `(base_url, api_key)`. Same shape as maintenance_copilot's client;
  embedding methods dropped (not needed).
- **`profile.py`** — Load a dataset (CSV / Excel / Parquet via pandas) and
  produce a compact profile: column names, dtypes, non-null counts, sample
  rows, and summary statistics. This profile is the grounding context handed to
  code generation (so the model never guesses column names).
- **`generate.py`** — Given the NL question + dataset profile (+ optional prior
  error / verifier hypotheses), prompt the `codegen` role to produce Python, and
  extract the code block from the response.
- **`guardrails.py`** — Static pre-execution gate. Reject code that does
  network I/O, spawns processes (`os.system`, `subprocess`), escapes the run
  directory, or performs unbounded/destructive filesystem writes. Returns a
  structured verdict (allow / block + reasons); blocked code never runs.
- **`sandbox.py`** — Execute approved code as a bounded local subprocess:
  wall-clock timeout, captured + size-capped stdout/stderr, working directory
  scoped to a per-run folder into which any figures are written. Returns
  `{status: text|error, stdout, stderr, figures: [...]}`.
- **`verify.py`** — Semantic verification. Given the question, the code, and the
  execution output, prompt the `verify` role to decide `OK` vs `REVISE` and
  return concrete repair hypotheses when revising. This is the semantic gate,
  not a syntax check (syntax failures are handled by the repair path).
- **`report.py`** — Compose a grounded Markdown report from the question, the
  verified output, and figure paths. References actual computed values; does not
  introduce claims absent from the output.
- **`audit.py`** — Append-only JSONL audit trail: question, dataset, generated
  code, execution status, verifier verdicts, retry counts, figure paths,
  timestamp. Same role as maintenance_copilot's `audit.py`.
- **`copilot.py`** — argparse CLI orchestrator. Subcommands:
  - `health` — verify the configured LLM endpoint(s) are reachable.
  - `profile <data>` — print the dataset profile as JSON.
  - `analyze <data> "<question>"` — run the full loop.
    Flags: `--max-repair` (default 3), `--max-verify` (default 2),
    `--out <dir>` (run/figures output dir). Model/endpoint selection is via the
    `DC_<ROLE>_*` env vars only — no per-run model flags, keeping one config path.
  - `audit [--limit N]` — print recent audit events.
  All subcommands print JSON (or a report path) to stdout, matching the
  maintenance_copilot convention.

## Supporting files

- **`SKILL.md`** — Frontmatter (`name: data_copilot`, one-line `description`) +
  problem framing, when-to-use, how-to-use (bash invocation examples), and a
  Guardrails section (bounded execution, grounding, no unverified answers).
- **`manifest.json`** — `display_name`, `tooltip`, `icon`, `dashboard` block,
  and `activity` labels for the `profile` and `analyze` actions. `subagent`
  disabled (matches maintenance_copilot).
- **`dashboard.html`** — Concept brief + the loop diagram, in the
  maintenance_copilot visual style.
- **`requirements.txt`** — Lean: `pandas`, `openpyxl` (Excel), `matplotlib`
  (charts), `openai`. No `torch` / `gradio` / `transformers` /
  `sentence_transformers` / `scikit-learn`. Auto-installed by the module
  registry's `install_module_deps` on load.
- **`icon.svg`**, **`.gitignore`** (ignore run outputs / `__pycache__`).
- **`sample_data/`** — a small demo CSV for the end-to-end test and dashboard
  examples (analogue of `maintenance_copilot/sample_manuals/`).

## Data flow

```
user question + dataset path
        │
   copilot.py analyze
        │
   profile.py ──► dataset profile (schema + stats)
        │
   generate.py ──► Python code
        │
   guardrails.py ──► allow / block
        │ (allow)
   sandbox.py ──► {stdout, stderr, figures}
        │           └─(error)─► generate.py (repair)  [≤ max-repair]
   verify.py ──► OK / REVISE(+hypotheses)
        │           └─(REVISE)─► generate.py (revise) [≤ max-verify]
        │ (OK / budget exhausted)
   report.py ──► grounded Markdown (+ figure links)
        │
   audit.py ──► append JSONL event
        │
   stdout: report path + JSON summary
```

## Error handling

- **Code error after `--max-repair`:** stop; report states the code could not be
  made to run and includes the last traceback. No fabricated result.
- **`REVISE` after `--max-verify`:** stop; report presents the last output
  labelled as *unverified* with the verifier's outstanding concerns.
- **Guardrail block:** the run aborts before execution; the reason is surfaced
  and audited. The agent may regenerate with a safer approach.
- **LLM/endpoint failure:** `copilot.py` exits non-zero with a JSON error;
  `health` exists to diagnose reachability up front.
- **Unreadable / unsupported dataset:** `profile.py` fails fast with a clear
  message before any LLM call.

## Testing

Per repo CLAUDE.md, both are required — unit tests **and** a real end-to-end run.

- **Unit tests** (`tests/`, `uv run pytest`) with a mocked `RoleClient`:
  - `profile.py`: schema/stats for CSV, Excel, Parquet; failure on bad input.
  - `guardrails.py`: blocks network/subprocess/fs-escape; allows benign pandas.
  - `sandbox.py`: enforces timeout and output cap; collects figures; scopes cwd.
  - `verify.py`: parses `OK`/`REVISE` + hypotheses from model output.
  - `copilot.py`: loop bounds honored; audit event shape; JSON output contract.
- **End-to-end** with `OPENAI_API_KEY`: `analyze` a small demo CSV with a real
  question, confirm it generates → runs → verifies → produces a grounded report
  and a figure, and writes an audit event.

## Reference map

For implementers, where each piece comes from in `.reference/data-agent`:

- Loop / edges — `langgraph_agent/graph.py`, `langgraph_agent/nodes.py`,
  `langgraph_agent/state.py`.
- Code generation & extraction — `triadic_dgm/agent/programmer.py`,
  `utils/utils.py::extract_code`, `nodes.generate_code`.
- Semantic verify — `triadic_dgm/agent/verifier.py`, `nodes.semantic_verify`.
- Report — `triadic_dgm/services/report_generator.py`, `nodes.generate_report`.
- Execution (reference used a Jupyter kernel; we replace it) —
  `triadic_dgm/sandbox/kernel.py`.
- Module conventions to match — `modules/maintenance_copilot/scripts/*`,
  `atria/core/modules/store.py` (module contract),
  `atria/core/modules/registry.py` (discovery + dep install).
