---
name: module_template
description: UI-only Embinder Module Federation dashboard. Minder owns chat and agent execution; no connector tools or backend APIs are provided.
---

# Module Template (UI-only)

This module supplies the `@embinder/react` dashboard surface at
`http://localhost:9300/dashboard/remoteEntry.js`.

It deliberately exposes no Python connector contract, tool, worker, module API,
registration endpoint, or heartbeat. Use Minder's own chat and agent runtime;
the dashboard's ghost cursor follows host tool lifecycle events.
