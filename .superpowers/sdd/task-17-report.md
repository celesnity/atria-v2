# Task 17 Report: `minder knowledge` CLI commands

## Files created/modified

- **Created** `minder/core/knowledge/cli_ops.py` — pure formatting functions `format_documents` and `format_hits`, transcribed verbatim from the brief.
- **Created** `minder/cli.py` — argparse-based `knowledge` subcommand group with `list`, `rescan`, `query`, `reingest`, `delete`.
- **Modified** `minder/serve.py` — added early dispatch: when `sys.argv[1] == "knowledge"`, delegates to `minder.cli.main` before the argparse web-server parser runs. This lets `minder knowledge --help` work without changing the existing `minder.serve:main` entry point in `pyproject.toml`.
- **Created** `tests/knowledge/test_cli.py` — two unit tests from the brief.

## Subcommand style

`minder-module` (`minder/module_dev.py`) uses `argparse.ArgumentParser` → `add_subparsers(dest="cmd")` → `add_parser(...)` → `set_defaults(func=cmd_<name>)` → `args.func(args)`. `minder/cli.py` follows the same pattern exactly, with an outer `knowledge` group and an inner second-level `add_subparsers(dest="knowledge_cmd")`.

## How `query` builds its provider

`wiring.py` does not export a provider factory directly, so `cmd_query` replicates the same construction pattern used internally by `build_knowledge_tool_spec_default`:

```python
sm = asyncio.run(get_sessionmaker())
repo = KnowledgeRepository(sm)
provider = DocumentsProvider(
    KnowledgeEmbedder(), repo, KnowledgeGraph(), lambda _ctx: tenant
)
results = provider.search(question, {"category": category}, k, SearchContext(None))
```

`SearchContext(None)` passes `user_id=None`; the lambda ignores the context and returns the CLI-supplied tenant, so the provider's tenant-guard is satisfied.

## Test outcome

2 passed in 0.01 s (`test_format_documents_table`, `test_format_hits_lists_citations`).
CLI smoke-check: `uv run minder knowledge --help` lists all five subcommands without error.
