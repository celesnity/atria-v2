<!--
name: 'Thinking: Available Tools'
description: Tool reference list for reasoning about possible actions
version: 1.0.0
priority: 45
-->

# Available Tools

Use this list to reason about what actions are possible. Suggest which tools to use in your reasoning.

- **Command Execution**: `run_command`
- **Documents**: `read_pdf`
- **User Interaction**: `ask_user`
- **Module UI Bridge**: `ui_describe`, `ui_act` when these tools are present in the current schema for a connected module.

Tool schemas are authoritative. Never propose or call a tool not included in
the current schema.
