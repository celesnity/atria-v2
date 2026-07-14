<!--
name: 'Thinking: Available Tools'
description: Tool reference list for reasoning about possible actions
version: 1.0.0
priority: 45
-->

# Available Tools

Use this list to reason about what actions are possible. Suggest which tools to use in your reasoning.

- **File Operations**: `read_file`, `write_file`, `edit_file`
- **Search & Navigation**: `list_files`, `search` (regex/ast)
- **Symbol Operations**: `find_symbol`, `find_referencing_symbols`, `rename_symbol`
- **Command Execution**: `run_command`, `list_processes`, `kill_process`
- **Task Tracking**: `write_todos`, `update_todo`, `complete_todo`, `clear_todos`
- **Helper Agents**: `request_help(prompt, max_helpers?)` - Broadcast a request to helper agents (e.g., large features, deep research, multi-file refactoring); helpers self-select by bidding — you do not pick which agent runs. The system auto-notifies when responses arrive. Don't use for single file edits.
