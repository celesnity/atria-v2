<!--
name: 'Tool Description: search_tools'
description: Discover and enable MCP tool schemas on demand
version: 1.0.0
-->

Search connected MCP servers for tools matching a query, without loading every
MCP tool's schema into context up front.

## When to use

- After the `## MCP Servers Connected` section lists a server, use this to find
  out what it can actually do before calling anything on it.
- Whenever you need an MCP tool whose schema isn't already visible in the
  current conversation.

## Usage notes

- `query`: search text matched against tool names and descriptions. Pass `"*"`
  or leave empty to list everything (optionally scoped by `server`).
- `detail_level`: `"names"` (just tool names), `"brief"` (name + one-line
  description, the default), or `"full"` (full parameter schemas — and the
  only level that actually enables the matched tools for use afterward).
- `server`: optional server name to scope the search to one MCP server; if
  omitted, the query text is checked for a server name mention first.
- Call again with `detail_level="full"` once you know which tool you need —
  `"names"`/`"brief"` results describe tools but do not enable them for use.
