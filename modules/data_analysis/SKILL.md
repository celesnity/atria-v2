# data_analysis

Agentic Data Analytics Platform for Engineering Datasets — local, file-
backed implementation of the PRD (v1.0, May 31 2026).

## ⛔ HARD RULES — read before every action

These rules prevent the two failure modes we've seen in the wild:
context-window blowups (47k+ tokens of raw data) and runtime errors
from ad-hoc code.

1. **DO NOT write inline Python (`python -c "..."`, here-docs).** Every
   step has a script. Pick one from the table below. Inline code keeps
   re-importing pandas/seaborn/numpy/matplotlib, loads full datasets
   into model context, and produces numpy/json/import errors that the
   agent cannot recover from.
2. **DO NOT `pip install`, `rm -rf .venv`, or recreate the venv.** The
   `da` launcher owns the venv — it is auto-bootstrapped and
   auto-updates on `requirements.txt` changes. Sandbox blocks manual
   removal; don't try.
3. **For chat-stream previews use `chart_png.py`; for dashboard/PDF use
   Vega-Lite (`chart.py` / `viz_agent.py`).** Both register a chart
   record under the same id so `pin` + `report` work either way. The
   PDF renderer auto-prefers PNG when present. NEVER call matplotlib /
   seaborn / plotly inline via `python -c "..."` — go through
   `chart_png.py create` so the chart record is persisted and the PNG
   lives at `<project>/charts/png/<chart_id>.png` (not in stdout).
4. **DO NOT `cat`, `head`, or `ls -lh` parquet files, raw CSVs, or
   saved chart spec JSON.** Their content blows context. Use the
   metadata in `dataset.json` / `artifact.json` instead — already
   compact.
5. **Always use the `da` launcher** at `<modules>/data_analysis/da`
   (auto-bootstraps venv with duckdb + openpyxl + markdown). Never
   call `python3 scripts/...` directly.
6. **For a user question against a project, prefer `answer.py`** —
   one call drives the whole Planner→Data→Viz→Insight→Trace loop and
   returns ≤ 400 bytes of JSON. Only fall back to step-by-step calls
   if the user wants iteration.

### Decision table — which script for what

| User wants… | Run this | Don't do this |
|---|---|---|
| Start a new file (one-shot) | `da scripts/agent.py onboard --slug … --path …` | Manual create + ingest + profile |
| "What's in this project?" | `da scripts/agent.py brief --slug …` | Sequence of list/schema calls |
| Find anomalies anywhere | `da scripts/agent.py scan --slug … --id …` | Pick a column then run anomalies |
| Suggest next steps | `da scripts/agent.py next --slug …` | Guess what to do |
| "Did we already answer this?" | `da scripts/agent.py recall --slug … --question …` | Re-run SQL blindly |
| Upload a CSV/XLSX | `da scripts/dataset.py ingest …` | `pd.read_csv` inline |
| Inspect a column | `da scripts/dataset.py schema --id …` | `df.describe()` inline |
| Run an aggregation | `da scripts/answer.py --slug … --question … --sql …` | Hand-write pandas pipeline |
| Build a chart (chat preview as PNG) | `da scripts/chart_png.py create --slug … --kind … --x … --y … --sql … --embed-data-uri` | `plt.bar`, `sns.pairplot` inline |
| Build a chart (dashboard/PDF, interactive) | `answer.py` (auto) or `viz_agent.py generate --save` | hand-rolled spec |
| Time-series anomalies on a known column | `da scripts/dataset.py anomalies --slug … --id … --time … --value …` | Eyeball outliers |
| Find a prior result | `da scripts/artifact.py search --query …` | Re-run SQL |
| Cross-dataset join | `da scripts/dataset.py relationships --slug …` then `sql.py save …` | Manual loop joins |
| Save result visible only in this chat | `da scripts/sql.py save … --scope chat` | Save everything project-wide |
| Generate a PDF report | `da scripts/report.py generate --slug … --out …` | Inline reportlab |
| Pin a chart + analysis to the in-progress report | `da scripts/agent.py pin --chart-id … --note "…"` | Re-render PDF each turn |
| Finish the loop → PDF with embedded charts | `da scripts/agent.py report --slug … --out …` | Manually stitch images |
| Quick-look a dataset | `da scripts/dataset.py read_dataset --limit 10` | `cat sales.csv` |
| Re-render the workspace | open `dashboard.html` in the host iframe | screenshots in stdout |

### Agentic loop (prefer this over step-by-step)

For a fresh project: `onboard` → `next` → execute one of the suggested moves →
`brief` to refresh context → repeat. Use `recall` before each new SQL to avoid
redoing work the project already remembers. `scan` substitutes for a Q&A turn
when the user asks "is anything weird here?" — no need to guess which column.

### Analyse-loop: chart → narrate in chat → pin → ... → PDF

For a "keep analysing until enough, then give me a report" request, drive this
loop yourself — don't ask the user when to stop. Each turn:

1. **Pick angle.** Use `agent.py next` (or your own judgement from `brief`).
   Don't reuse anything `recall` already returned a confident hit for.
2. **Build chart with PNG preview** (so the user sees it inline in chat this
   turn, not later in a PDF):
   ```
   da scripts/chart_png.py create \\
       --slug <s> --kind bar|line|scatter|hist|pie \\
       --x <col> --y <col> --title "<short>" \\
       --sql "<DuckDB SQL>" --embed-data-uri
   ```
   Output JSON contains `chart_id`, `png_path`, `data_uri`.
3. **Reply to the user** in a single chat message containing, in order:
   - a one-line header (`### Finding: <name>`),
   - the SQL block:
     ````
     ```sql
     <the SQL you just ran>
     ```
     ````
   - the chart image: `![chart](data:image/png;base64,...)` using the
     `data_uri` from step 2 (paste it verbatim — chat renderer is GFM-markdown
     and supports data URIs),
   - 2-4 sentences of analysis: what changed, why it matters, what it implies.
4. **Pin it** so the report keeps it:
   ```
   da scripts/agent.py pin --slug <s> --chart-id <chart_id> \\
       --note "<the same 2-4 sentence analysis>"
   ```
5. **Decide whether to keep going.** Stop when: the next 2 `next` moves look
   redundant; pinned charts already answer the user's question end-to-end; the
   user says enough. Default cap ~6 pins before checking in with the user.
6. **Finish → PDF:** `da scripts/agent.py report --slug <s> --out /tmp/report.pdf`.
   The PDF embeds the same PNGs (Chrome inlines `<img>` at print time) with the
   notes underneath. Return the PDF path to the user.

Why PNG-in-chat + Vega-Lite-on-dashboard:
- Chat needs a 1-turn preview — base64 PNG in markdown is the cheapest.
- The dashboard/iframe still has the underlying Vega-Lite spec for interactive
  zoom (chart records carry both when produced via `chart.py spec --save`).
- The PDF report auto-uses PNG when `png_path` is set on the chart record
  (which `chart_png.py` does), so there's no double-render at print time.

Scope rule: when the report should be tied to *this* conversation only,
pass `--scope chat` to both `pin` and `report` (uses `$ATRIA_SESSION_ID`).

If a tool is missing, **say so explicitly** instead of writing inline
Python to fill the gap — the user can extend the module.

## 🪟 Rolling context window — `context.py`

The host loop's raw conversation history grows with every tool output
and will cross the 64k limit after ~5 SQL/chart roundtrips. Don't try
to fix this by trimming individual tool outputs further — instead,
**replace the raw history with a compact envelope** built from the
project workspace.

```
# Once per turn — auto-rolls older messages if conversation > 20 turns,
# then emits a budgeted JSON envelope (~750 tokens for a typical project).
da scripts/context.py auto --slug <slug> --keep-last 5 --threshold 20 --max-tokens 2000
```

Envelope shape:

```jsonc
{
  "project": { "slug": "...", "name": "..." },
  "memory": [ "Q: …", "A: saved art_…" ],          // older turns, 1 line each
  "catalog": {
    "datasets":  [ {id, name, rows, n_cols} … ],
    "artifacts": [ {id, title, question, row_count, cols[:6]} … ],
    "charts":    [ {id, title, kind, artifact_id} … ]
  },
  "recent_traces":   [ {id, query, summary, tools} … ],
  "recent_dialogue": [ {role, content, ts} … ],     // last K pairs verbatim
  "hints": [ "Refer to artifacts by id — never re-read raw data." ],
  "tokens_est": 746
}
```

Token budget is enforced top-down: when over budget the envelope trims
oldest memory → oldest artifact → oldest dialogue → shortens questions,
in that order. `--max-tokens` is a hard ceiling.

Two variants if you need finer control:

```
da scripts/context.py envelope --slug <slug>               # build only
da scripts/context.py rollup   --slug <slug> --keep-last 8 # physical truncate
```

`rollup` rewrites `conversation.jsonl` to the last N pairs and appends
older turns (one-line summarised) to `memory.jsonl`. Memory is
preserved forever; the live conversation stays small.

**The host's main loop should call `context.py auto` before each LLM
call and feed the envelope as system context instead of raw history.**
Any detail the model needs is one re-fetch away by id
(`artifact.py show`, `sql.py run`, `dataset.py schema`).

The module wraps the four PRD agents (Planner, Data, Viz, Insight) as
CLI tool surfaces over a Project workspace. Datasets are ingested to
Parquet and queried via DuckDB; artifacts are persisted as Parquet +
JSON metadata; every query turn produces a user-visible Execution Trace.

## When to use

- User asks to analyze CSV / XLSX engineering datasets.
- User wants conversational analytics: "Which region drives revenue?",
  "Show me defect trend over time", "Compare this month against last".
- User wants charts pinned to a persistent workspace.
- User invokes `/brainstorming` or asks for proactive insights.
- User has multiple files and asks for a cross-dataset join.

## Where data is stored — per chat, NEVER inside the module

Project workspaces live next to the **conversation**, not next to the
module. The storage root is resolved at runtime in this order:

1. `$ATRIA_DA_ROOT` — explicit override (its `projects/` subdir is used).
2. `$ATRIA_WORKSPACE` — the chat session's working directory (preferred;
   exported by the host on every Bash call).
3. `$ATRIA_SESSION_DIR` — fallback name some hosts use.
4. `$CWD/.data_analysis/` — last resort.

So a typical layout for one chat is:

```
<chat workspace>/.data_analysis/projects/
  index.json
  <slug>/
    project.json
    conversation.jsonl
    datasets/<id>.json + <id>.parquet + raw/<id>.<ext>
    artifacts/<id>.json + <id>.parquet
    charts/<id>.json
    traces/<id>.json
```

The module directory (`<modules>/data_analysis/data/`) is **read-only
sample data only**. Never write project state there — different chats
must not share workspaces.

## Workspace layout (per project)

```
project.json            — id, name, description, timestamps
conversation.jsonl      — the single Project conversation (FR-PROJ-02)
datasets/
  <id>.json             — schema + column profile
  <id>.parquet          — ingested data (FR-DS-03)
  raw/<id>.<ext>        — original CSV/XLSX kept for traceability
artifacts/
  <id>.json             — title, question, sql, columns, row_count, tags
  <id>.parquet          — result table (FR-DATA-05)
charts/
  <id>.json             — Vega-Lite spec + artifact_id back-link
traces/
  <id>.json             — query, plan, actions, sql, tools, artifacts, summary
```

A flat `data/projects/index.json` is kept in sync so the dashboard can
render the whole workspace without listing directories.

## Context-window protection rules — read before every call

LLM context windows blow up when scripts echo raw data. The module is
engineered so the agent **never needs to see full rows**. Stick to these
rules and a 64k-token model handles datasets of any practical size:

1. **Never `cat` parquet, raw CSV, or saved chart spec JSON.** The model
   doesn't need their content; it needs the metadata, which already
   lives in `dataset.json` / `artifact.json`.
2. **Never `ls -lh` the whole project tree.** Use `project.py show
   --slug …` — it returns a compact summary of all four panels.
3. **Always pass `--save` to `chart.py spec` and `viz_agent.py
   generate`.** Without `--save` the script intentionally elides the
   embedded `data.values` array and prints a small receipt; with
   `--save` it writes the full spec to disk and prints only the path.
4. **For SQL, prefer `sql.py run --text` for inspection** (compact
   table, capped at 20 rows by default) and `sql.py save` to
   materialise as an artifact when results matter. The JSON mode is
   also capped — pass `--full` only when downstream code (not the
   LLM) consumes the output.
5. **Don't read whole artifact parquets.** Run another SQL `LIMIT`-ed
   query against the artifact when you need a peek.
6. **Use `artifact.py search`/`retrieve` instead of listing**, so the
   model only sees relevant prior work, not the entire artifact log.

Per-script defaults (hard ceilings, even if a caller passes larger
`--limit`):

| Tool | Default cap | Hard ceiling |
|------|-------------|--------------|
| `analyze.py head -n` | 5 | 20 |
| `dataset.py read_dataset --limit` | 10 | 100 |
| `sql.py run --limit` (JSON & text) | 20 | (use `--full`) |
| `artifact.py show --head` | 5 | 20 |
| `chart.py spec` (no `--save`) | data elided | — |
| `viz_agent.py generate` (no `--save`) | data elided | — |

## Tool surfaces (PRD §9)

Bash CWD is the chat workspace. Replace `<modules>` with the absolute
modules root announced at the top of the "Active Module Skills" prompt
section.

### Project (FR-PROJ-*)
```
python <modules>/data_analysis/scripts/project.py list
python <modules>/data_analysis/scripts/project.py create --name "Q1 Analysis"
python <modules>/data_analysis/scripts/project.py show --slug q1-analysis
```

### Datasets — `dataset.py` (FR-DS-* and Data Agent surface)
```
# Ingest CSV / TSV / XLSX → Parquet, profile column types + cardinality.
python <modules>/data_analysis/scripts/dataset.py ingest \
  --slug q1-analysis --path ./sales.csv --name sales

# Inspect + tool surfaces.
python <modules>/data_analysis/scripts/dataset.py list --slug q1-analysis
python <modules>/data_analysis/scripts/dataset.py schema --slug q1-analysis --id ds_abc
python <modules>/data_analysis/scripts/dataset.py read_dataset --slug q1-analysis --id ds_abc --limit 50

# Cross-dataset join discovery with confidence scoring (FR-DATA-04).
python <modules>/data_analysis/scripts/dataset.py relationships --slug q1-analysis
# decision: auto (≥0.75) | suggest (0.4–0.75) | dropped (<0.4)
```

Datasets are read-only after ingest (FR-DS-04).

### Data Agent SQL — `sql.py`
DuckDB SQL dialect (FR-SQL-04). Datasets are registered as views named
after their `--name`.

```
# Visible, re-runnable SQL (FR-SQL-01, FR-SQL-02). Use @file for long SQL.
python <modules>/data_analysis/scripts/sql.py run \
  --slug q1-analysis \
  --sql "SELECT region, SUM(revenue) AS total FROM sales GROUP BY region" \
  --text

# Persist as an Artifact (FR-DATA-05, FR-ART-01).
python <modules>/data_analysis/scripts/sql.py save \
  --slug q1-analysis \
  --title "Revenue by region" \
  --question "Which region drives revenue?" \
  --sql "SELECT region, SUM(revenue) AS total FROM sales GROUP BY region"

# Record an Execution Trace (FR-TRACE-*). No chain-of-thought.
python <modules>/data_analysis/scripts/sql.py trace \
  --slug q1-analysis \
  --query "Which region drives revenue?" \
  --plan '[{"agent":"data","tool":"execute_sql"}]' \
  --tools execute_sql,save_artifact \
  --artifacts art_2a72 \
  --summary "East leads with 35% of total revenue"
```

### Artifact memory — `artifact.py` (FR-ART-*)
```
python <modules>/data_analysis/scripts/artifact.py list --slug q1-analysis
python <modules>/data_analysis/scripts/artifact.py show --slug q1-analysis --id art_2a72
python <modules>/data_analysis/scripts/artifact.py search   --slug q1-analysis --query "region revenue"
python <modules>/data_analysis/scripts/artifact.py retrieve --slug q1-analysis --query "..." --top-k 3
```

`search` / `retrieve` use BM25-lite lexical scoring over the artifact's
title + question + SQL + columns. (PRD calls for vector similarity —
upgrade path is to plug `sentence-transformers` into `core/retrieve.py`
without changing the public API.)

### Agents

**Planner** (`agents/planner.py`, FR-PLAN-*) — proposes an execution
plan from the user query. Includes clarifying questions, retrieved
artifacts, and a typed list of steps. Does NOT branch — the main LLM
decides what to execute, in what order.
```
python <modules>/data_analysis/scripts/agents/planner.py \
  --slug q1-analysis --query "Show revenue trend per region"
```

**Visualization Agent** (`agents/viz_agent.py`, FR-VIZ-*) — recommends
chart types from an artifact's column shape, and renders Vega-Lite
specs. Does NOT interpret data (FR-VIZ-04).
```
python <modules>/data_analysis/scripts/agents/viz_agent.py recommend \
  --slug q1-analysis --artifact-id art_2a72

python <modules>/data_analysis/scripts/agents/viz_agent.py generate \
  --slug q1-analysis --artifact-id art_2a72 \
  --kind bar --x region --y total --save
```

**Insight Agent** (`agents/insight_agent.py`, FR-INS-*) — anomaly
detection, summary observations, and comparison against historical
artifacts.
```
python <modules>/data_analysis/scripts/agents/insight_agent.py detect_anomaly \
  --slug q1-analysis --artifact-id art_2a72
python <modules>/data_analysis/scripts/agents/insight_agent.py summarise_results \
  --slug q1-analysis --artifact-id art_2a72
python <modules>/data_analysis/scripts/agents/insight_agent.py compare \
  --slug q1-analysis --artifact-id art_now --against art_last_month
```

### Chat blocks (push to UI)

`push_chart.py` and `brainstorm.py` still work as before, and now align
with the Project workspace once you pass `--path` pointing at a project
dataset's parquet (or any standalone CSV). The dashboard at
`dashboard.html` renders the active project's Datasets / Artifacts /
Charts canvas / Traces in four panels.

## Standard agent loop (PRD §5.10 User Journey)

When the user asks a natural-language question in a Project, run:

1. `planner.py --slug … --query …` — get plan + retrieved artifacts.
2. If `ambiguities` is non-empty, ask the user before continuing
   (FR-PLAN-03). Do not guess.
3. If a retrieved artifact already answers the question, reuse it
   (FR-ART-02) — call `artifact.py show` and `viz_agent.py recommend`.
4. Otherwise: write DuckDB SQL, run `sql.py save` to materialise the
   answer as an Artifact.
5. `viz_agent.py recommend` → pick a chart kind → `viz_agent.py
   generate ... --save`.
6. `insight_agent.py detect_anomaly` + `summarise_results` to surface
   proactive observations (FR-INS-03).
7. `sql.py trace` to record the full Execution Trace.
8. Append the user turn + assistant summary to the project's
   `conversation.jsonl` (via `core.workspace.append_message`).

Never hard-code if/else branches across these steps — the LLM picks the
next step from the prior step's output.

## Files

- `manifest.json` · `icon.svg` · `dashboard.html` — UI surface.
- `blocks/chart_preview.html` · `blocks/brainstorm.html` — push blocks.
- `scripts/context.py` — **rolling-window envelope** (`auto` /
  `envelope` / `rollup`). Replaces 47k-token raw history with ~750
  tokens of structured project state. Call once per host turn.
- `scripts/answer.py` — **one-shot question→answer pipeline.** Drives
  the full PRD loop and returns a ~400-byte JSON receipt
  (`artifact_id` · `chart_id` · `summary` · `trace_id`). This is the
  default entry point for "ask a question of project X".
- `scripts/report.py` — Markdown → PDF (cover + body + embedded
  charts via `![[chart_id]]` syntax). `render` for hand-written MD;
  `generate` for auto project digest.
- `scripts/project.py` · `dataset.py` · `sql.py` · `artifact.py` —
  workspace + Data Agent tools.
- `scripts/agents/planner.py` · `viz_agent.py` · `insight_agent.py` —
  the three PRD agents that orbit the Data Agent.
- `scripts/core/workspace.py` — JSON-backed metadata stores + project
  index (rebuilt on every write).
- `scripts/core/duck.py` — DuckDB lazy connect, CSV/XLSX→Parquet
  ingest, `execute_sql`, `profile_parquet`.
- `scripts/core/relationships.py` — confidence-scored cross-dataset
  join discovery.
- `scripts/core/retrieve.py` — BM25-lite artifact retrieval.
- `scripts/analyze.py` · `chart.py` · `dashboard.py` · `brainstorm.py`
  · `push_chart.py` — original tabular toolset; still useful for ad-hoc
  one-shot exploration outside a Project.
- `data/projects/<slug>/…` — per-project workspace.
- `data/projects/index.json` — flat catalog the dashboard reads.

## Dependencies — self-bootstrapping launcher

The module ships a `da` launcher at its root that owns a local
`.venv/` next to itself. First invocation creates the venv and
installs `requirements.txt` (duckdb + openpyxl) automatically;
subsequent runs re-exec straight into the venv with zero overhead.

**Prefer the launcher over bare `python` for every script in this
module** — it guarantees dependencies are present regardless of the
caller's Python environment.

```
# Always-on canonical form:
<modules>/data_analysis/da scripts/project.py list
<modules>/data_analysis/da scripts/dataset.py ingest --slug q1 --path …
<modules>/data_analysis/da scripts/sql.py run --slug q1 --sql "…"
<modules>/data_analysis/da scripts/agents/planner.py --slug q1 --query "…"

# Forward arbitrary commands to the venv's interpreter:
<modules>/data_analysis/da -m pip install sentence-transformers
<modules>/data_analysis/da -c "import duckdb; print(duckdb.__version__)"

# Reset the venv (forces re-bootstrap on next call):
<modules>/data_analysis/da --reset
```

The launcher tracks `requirements.txt` by SHA-256, so editing the
requirements file triggers a one-time reinstall on the next call —
nothing else to remember. Pick the base interpreter for venv creation
with `DA_PYTHON=/path/to/python3.12 <modules>/data_analysis/da …`.

The pre-existing `analyze.py` / `chart.py` toolset still works without
any install for plain CSV, but using `da` is fine for those too.

## Alignment with PRD non-goals

- Datasets are read-only — no edit/delete (FR-DS-04).
- Artifacts have no editing / deletion / versioning (FR-ART-04/05).
- The dashboard surfaces datasets + artifacts + charts canvas + traces
  for transparency; it is not a BI dashboard builder, and only renders
  what agents already produced.
- Multi-user / RBAC / OAuth / scheduled analysis are not implemented
  (PRD §10.2).
