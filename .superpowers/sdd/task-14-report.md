# Task 14 Report: knowledge_query ToolSpec + registry wiring

## ToolSpec Shape (minder/core/skill_tools.py)

`ToolSpec` is a `@dataclass` with these fields:
- `name: str`
- `description: str`
- `parameters: dict[str, Any]`
- `handler: Callable[..., dict[str, Any]]`
- `card_path: Path | None = None`  ← optional, not needed

The brief's `ToolSpec(...)` call matches the real constructor exactly — no adaptation needed.

## Files Created / Modified

- **Created** `minder/core/knowledge/tool.py` — `build_knowledge_tool_spec(provider, resolve_context)` returns a `ToolSpec` named `knowledge_query` with params `{question (required), category (enum), k (int)}`. Tenant is never a model parameter; it comes from `resolve_context()`.
- **Created** `minder/core/knowledge/wiring.py` — `build_knowledge_tool_spec_default()` returns `None` if `DATABASE_URL` is unset; otherwise wires `DocumentsProvider` from env and returns the `ToolSpec`.
- **Modified** `minder/core/context_engineering/tools/registry.py` — inserted try/except block after the skill-spec merge loop (after line 206) to register the knowledge tool into `_skill_specs` + `_handlers`. Failures are logged as warnings, never fatal.

## Test Results

- `tests/knowledge/test_tool.py`: **2 passed** (TDD cycle: red → green)
- `tests/knowledge/` full suite: **40 passed**
- `tests/ -k registry` (excluding pre-existing broken collection files): **12 passed, 0 failed**
- Pre-existing collection errors in `tests/search/` and `tests/test_ai_workspace_*.py` are unrelated to this task (missing optional deps); they were already broken before this task.

## Notes

The `ToolSpec` constructor was transcribed verbatim from the brief — no adaptation was needed since the real class shape matches exactly (4 required fields + 1 optional `card_path`).
