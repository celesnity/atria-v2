# module_template — Embinder UI-only template

`module_template` is a cross-origin Module Federation dashboard built with
`@embinder/react` from the local, untracked `minderSDK/` checkout.

It intentionally contains no Python connector SDK, connector contract,
registration or heartbeat, Celery worker, persistence service, or module REST
API. Minder owns the agent, chat, approvals and WebSocket. The module renders
the UI surface and its Embinder ghost cursor follows host tool lifecycle events.

## Run

Start the core stack first, then build and run the static remote:

```bash
docker compose -f modules/module_template/docker-compose.yml up -d --build
```

Minder loads the dashboard from:

```text
http://localhost:9300/dashboard/remoteEntry.js
```

The only endpoint is the static liveness response:

```text
GET http://localhost:9300/connector/health
```
