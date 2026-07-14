# Classify-First Todo Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main agent classify every request as single-step vs multi-step and, when multi-step, emit one brief line then create a todo list before executing.

**Architecture:** Pure prompt-text change. The rule lives in the existing `main-task-tracking.md` system-prompt section (registered in `composition.py` at priority 55) with a one-line cross-reference added to `main-interaction-pattern.md`. No tool or Python logic changes — `write_todos`/`update_todo`/`complete_todo`/`clear_todos` already exist. Verified by a unit test that composes the main prompt and asserts the new wording is present.

**Tech Stack:** Python, pytest, markdown prompt sections, `PromptComposer` (`minder/core/agents/prompts/composition.py`).

## Global Constraints

- System prompts must NOT use table format — use prose, bullets, or sections (project CLAUDE.md).
- Line length 100 chars for Python; Google-style docstrings.
- Threshold wording, used verbatim: **"2+ distinct actions"**.
- Multi-step preamble example, used verbatim: **"This is multi-step — planning it out:"**.
- Run tests with `uv run --no-sync pytest` (project convention for this repo).

---

### Task 1: Add the classify-first rule to the task-tracking prompt section, guarded by a test

**Files:**
- Modify: `minder/core/agents/prompts/templates/system/main/main-task-tracking.md`
- Modify: `minder/core/agents/prompts/templates/system/main/main-interaction-pattern.md`
- Create: `tests/test_classify_first_prompt.py`

**Interfaces:**
- Consumes: `create_composer(templates_dir: Path, mode: str = "system/main") -> PromptComposer` from `minder.core.agents.prompts.composition`; `PromptComposer.compose(context: Dict[str, Any]) -> str`.
- `templates_dir` resolves to `minder/core/agents/prompts/templates` (see `minder/core/agents/components/prompts/builders.py:140`).
- Produces: nothing consumed by later tasks (final task).

- [ ] **Step 1: Write the failing test**

Create `tests/test_classify_first_prompt.py`:

```python
"""The composed main system prompt must instruct classify-first todo behavior."""

from pathlib import Path

from minder.core.agents.prompts.composition import create_composer

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent
    / "minder/core/agents/prompts/templates"
)


def _compose_main_prompt() -> str:
    composer = create_composer(TEMPLATES_DIR, "system/main")
    return composer.compose({})


def test_prompt_states_2plus_distinct_actions_threshold():
    prompt = _compose_main_prompt()
    assert "2+ distinct actions" in prompt


def test_prompt_requires_classify_first():
    prompt = _compose_main_prompt()
    assert "Classify First" in prompt


def test_prompt_requires_todos_before_executing_multistep():
    prompt = _compose_main_prompt()
    lowered = prompt.lower()
    assert "before" in lowered and "write_todos" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_classify_first_prompt.py -v`
Expected: FAIL — `test_prompt_states_2plus_distinct_actions_threshold` and `test_prompt_requires_classify_first` assert on wording not yet present (the current section says "multi-file changes", not "2+ distinct actions", and has no "Classify First" heading).

- [ ] **Step 3: Rewrite the task-tracking section**

Replace the entire contents of `minder/core/agents/prompts/templates/system/main/main-task-tracking.md` with:

```markdown
<!--
name: 'System Prompt: Task Tracking'
description: Classify-first todo workflow for multi-step work
version: 3.0.0
-->

# Task Tracking

## Classify First

Before acting on any request, classify it as single-step or multi-step. A request is **multi-step** when it needs **2+ distinct actions** (for example: read then edit, an edit spanning two files, or a build/test/fix cycle). A request is single-step when it is answerable in one shot: a plain answer, a greeting, a question, or a one-shot single-file edit.

- **Multi-step:** first emit ONE brief line signaling the plan (for example: "This is multi-step — planning it out:"), then call `write_todos` to create the FULL todo list BEFORE taking any state-changing action, then execute strictly in todo order.
- **Single-step:** just do it — no todo list, no preamble.

## Workflow

1. Create todos ONCE at start with `write_todos` (all start as `pending`)
2. Work through todos IN ORDER:
   - `update_todo(id, status="in_progress")` when starting
   - Do the work
   - `complete_todo(id)` when finished
3. Keep only ONE todo `in_progress` at a time
4. **NEVER skip todos** - if work was done implicitly, mark it complete
5. **The system will remind you if todos remain incomplete when you try to finish**
6. If the user cancels or abandons tasks, call `clear_todos` to remove the entire list

## When to Use

✅ Any request needing 2+ distinct actions
✅ Multi-file changes
✅ Feature implementation with multiple steps
✅ Build/test/fix cycles
❌ Single-step requests (one plain answer, greeting, question, or one-shot single-file edit)

## Formatting

Todo content must be plain text — no markdown (no bold, italic, backticks, or links). The system strips markdown automatically, so formatting is wasted tokens.
```

- [ ] **Step 4: Add the cross-reference in the interaction-pattern section**

In `minder/core/agents/prompts/templates/system/main/main-interaction-pattern.md`, replace this line (step 1, "Understand first"):

```markdown
1. **Understand first**: Before you change anything, be sure you understand the request and the current state. If you are missing context, read it — batch the read-only calls (read_file, list_files, search) in one response so you see the whole picture before deciding. Do not act on assumption.
```

with (adds one trailing sentence pointing to Task Tracking):

```markdown
1. **Understand first**: Before you change anything, be sure you understand the request and the current state. If you are missing context, read it — batch the read-only calls (read_file, list_files, search) in one response so you see the whole picture before deciding. Do not act on assumption. As part of understanding, classify the request as single-step or multi-step (see Task Tracking) — multi-step means 2+ distinct actions and requires a todo list before you execute.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --no-sync pytest tests/test_classify_first_prompt.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Run the existing prompt test to confirm no regression**

Run: `uv run --no-sync pytest tests/test_blackboard_prompt_append.py -v`
Expected: PASS (unchanged — this task does not touch blackboard prompt logic).

- [ ] **Step 7: Commit**

```bash
git add minder/core/agents/prompts/templates/system/main/main-task-tracking.md \
        minder/core/agents/prompts/templates/system/main/main-interaction-pattern.md \
        tests/test_classify_first_prompt.py
git commit -m "feat(prompt): classify-first todo workflow for multi-step requests"
```

---

## Notes

- No `composition.py` change is needed: `main-task-tracking.md` is already registered (priority 55) and `main-interaction-pattern.md` at priority 42, so edited content is picked up automatically.
- Per project convention, omit any `Co-Authored-By: Claude` trailer from the commit.
