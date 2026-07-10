"""Starter files for the ``service`` module template.

Scaffolds a complete, runnable service-module (connector backend + Module
Federation dashboard + manifest + compose snippet) built on ``atria-module-sdk``.
Kept out of ``store.py`` so the (large) starter strings don't bury the CRUD.

See docs/connector-contract.md and docs/module_integration guide.
"""
from __future__ import annotations

import json


def _title(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").title()


def skill_md(name: str, summary: str) -> str:
    title = _title(name)
    body = summary or f"{title} — a service module answering questions via its connector."
    return (
        f"---\n"
        f"name: {name}\n"
        f"description: {body} Always answer via the `{name}_query` tool; do not "
        f"answer from your own knowledge.\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"{body}\n\n"
        f"## When to use\n"
        f"- Describe the trigger conditions for this module.\n\n"
        f"## How to use\n"
        f"Always answer via the `{name}_query` tool. It runs the module's connector "
        f"service (out-of-process) and returns a structured, card-rendered answer. "
        f"If the tool reports the service is unavailable, relay that and stop — do "
        f"not answer from your own knowledge.\n"
    )


def manifest_json(name: str, port: int) -> str:
    title = _title(name)
    payload = {
        "display_name": title,
        "tooltip": f"Open the {title} module",
        "icon": "icon.svg",
        "dashboard": {
            "title": f"{title} · dashboard",
            "default_height": 720,
            "badge_color": "info",
        },
        "service": {
            "connector_url": f"http://{name.replace('_', '-')}:{port}",
            "health_path": "/connector/health",
            "streaming": False,
            "tools": [
                {
                    "name": f"{name}_query",
                    "description": f"Answer a {title} question and render it as a card.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The question."}
                        },
                        "required": ["query"],
                    },
                }
            ],
        },
        "remote": {
            "name": name,
            "remoteEntry": f"http://localhost:{port}/dashboard/remoteEntry.js",
            "exposed": {"dashboard": "./Dashboard"},
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def backend_app_py(name: str) -> str:
    return (
        '"""Connector service for the {name} module — built on atria-module-sdk.\n\n'
        "The SDK generates the whole /connector/* contract from the decorated\n"
        "handlers below; this file never imports ``atria``.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "from atria_module_sdk import Connector, ServiceUnavailable, card\n\n"
        "import service  # backend/service.py — your pure business logic\n\n"
        'conn = Connector("{name}", version="1")\n\n\n'
        '@conn.tool(\n'
        '    "{name}_query",\n'
        '    description="Answer a {name} question and render it as a card.",\n'
        "    parameters={{\n"
        '        "type": "object",\n'
        '        "properties": {{"query": {{"type": "string"}}}},\n'
        '        "required": ["query"],\n'
        "    }},\n"
        '    card_type="{name}_answer",\n'
        ")\n"
        "def query(query: str, **kwargs) -> dict:\n"
        '    """Answer a question. Raise ServiceUnavailable(\\"<sidecar>\\") if a\n'
        '    downstream dependency is down — the SDK fails closed for you."""\n'
        "    result = service.run_query(query)\n"
        '    return {{"output": result, "card": card(result, card_type="{name}_answer")}}\n\n\n'
        "@conn.health_probe\n"
        "def probe() -> dict:\n"
        '    return {{"logic": "ok"}}\n\n\n'
        "app = conn.asgi()\n"
    ).format(name=name)


def backend_service_py(name: str) -> str:
    return (
        '"""Pure business logic for the {name} connector — no ``atria`` import.\n\n'
        "Put retrieval / models / heavy deps here. app.py only shapes this into the\n"
        "connector HTTP contract.\n"
        '"""\n'
        "from __future__ import annotations\n\n\n"
        "def run_query(query: str) -> str:\n"
        '    """Replace with real logic (RAG, model call, DB lookup, …)."""\n'
        '    return f"You asked: {{query!r}}. Wire up real logic in backend/service.py."\n'
    ).format(name=name)


def backend_requirements() -> str:
    return (
        "# fastapi + pydantic + the whole /connector/* contract come from\n"
        "# atria-module-sdk (installed from the repo root in the Dockerfile).\n"
        "# Add the module's own heavy deps below.\n"
        "uvicorn[standard]>=0.29\n"
    )


def backend_dockerfile(name: str, port: int) -> str:
    return (
        "# Build context is the REPO ROOT (see docker-compose.snippet.yml) so the\n"
        "# image can install the shared atria_module_sdk from the repo root.\n\n"
        "# --- frontend build stage ---\n"
        "FROM node:20-slim AS fe\n"
        "WORKDIR /fe\n"
        f"COPY modules/{name}/frontend/package.json modules/{name}/frontend/package-lock.json* ./\n"
        "RUN npm install\n"
        f"COPY modules/{name}/frontend/ ./\n"
        "RUN npm run build\n\n"
        "# --- python service stage ---\n"
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n\n"
        "# Shared connector SDK first (own layer, rarely changes).\n"
        "COPY atria_module_sdk /sdk\n"
        "RUN pip install --no-cache-dir /sdk\n\n"
        "# Module's own heavy deps.\n"
        f"COPY modules/{name}/backend/requirements.txt ./\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
        f"COPY modules/{name}/backend/ /app\n"
        "COPY --from=fe /fe/dist /app/frontend_dist\n"
        f"ENV PYTHONUNBUFFERED=1 MODULE_PUBLIC_BASE=http://localhost:{port} \\\n"
        "    MODULE_DASHBOARD_DIST=/app/frontend_dist\n"
        f"EXPOSE {port}\n"
        f'CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "{port}"]\n'
    )


def frontend_package_json(name: str) -> str:
    payload = {
        "name": f"{name.replace('_', '-')}-frontend",
        "private": True,
        "type": "module",
        "scripts": {"build": "vite build", "dev": "vite"},
        "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
        "devDependencies": {
            "@module-federation/vite": "^1.16.14",
            "@vitejs/plugin-react": "^4.3.1",
            "typescript": "^5.4.0",
            "vite": "^5.1.4",
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def frontend_vite_config(name: str, port: int) -> str:
    return (
        "import { defineConfig } from 'vite';\n"
        "import react from '@vitejs/plugin-react';\n"
        "import { federation } from '@module-federation/vite';\n\n"
        "export default defineConfig({\n"
        "  plugins: [\n"
        "    react(),\n"
        "    federation({\n"
        f"      name: '{name}',\n"
        "      filename: 'remoteEntry.js',\n"
        "      exposes: { './Dashboard': './src/DashboardApp.tsx' },\n"
        "      shared: {\n"
        "        react: { singleton: true, requiredVersion: '^18.3.1' },\n"
        "        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },\n"
        "      },\n"
        "    }),\n"
        "  ],\n"
        "  build: { outDir: 'dist', target: 'esnext' },\n"
        f"  server: {{ origin: 'http://localhost:{port}' }},\n"
        "});\n"
    )


def frontend_tsconfig() -> str:
    payload = {
        "compilerOptions": {
            "target": "esnext",
            "module": "esnext",
            "moduleResolution": "bundler",
            "jsx": "react-jsx",
            "strict": True,
            "skipLibCheck": True,
            "esModuleInterop": True,
        },
        "include": ["src"],
    }
    return json.dumps(payload, indent=2) + "\n"


def frontend_index_html(name: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "  <meta charset=\"utf-8\" />\n"
        f"  <title>{name} dashboard</title>\n"
        "</head>\n<body>\n  <div id=\"root\"></div>\n"
        "  <script type=\"module\" src=\"/src/DashboardApp.tsx\"></script>\n"
        "</body>\n</html>\n"
    )


def frontend_dashboard_tsx(name: str) -> str:
    title = _title(name)
    return (
        "import { useEffect, useState } from 'react';\n\n"
        "interface DashboardProps {\n"
        "  /** Connector public base, injected by the Atria host. */\n"
        "  apiBase: string;\n"
        "}\n\n"
        "/**\n"
        f" * The {name} dashboard, rendered natively inside the Atria host via\n"
        " * Module Federation (no iframe). It talks to its own connector directly.\n"
        " */\n"
        "export default function DashboardApp({ apiBase }: DashboardProps) {\n"
        "  const [online, setOnline] = useState<boolean | null>(null);\n"
        "  const [q, setQ] = useState('');\n"
        "  const [answer, setAnswer] = useState('');\n\n"
        "  useEffect(() => {\n"
        "    fetch(`${apiBase}/connector/health`)\n"
        "      .then((r) => r.json())\n"
        "      .then((h) => setOnline(!!h.ok))\n"
        "      .catch(() => setOnline(false));\n"
        "  }, [apiBase]);\n\n"
        "  async function ask() {\n"
        "    const r = await fetch(`${apiBase}/connector/tools/" + name + "_query`, {\n"
        "      method: 'POST',\n"
        "      headers: { 'content-type': 'application/json' },\n"
        "      body: JSON.stringify({ arguments: { query: q } }),\n"
        "    });\n"
        "    const res = await r.json();\n"
        "    setAnswer(typeof res.output === 'string' ? res.output : JSON.stringify(res.output));\n"
        "  }\n\n"
        "  return (\n"
        "    <div style={{ padding: 16 }}>\n"
        f"      <h2>{title}</h2>\n"
        "      <p>Service: {online === null ? 'checking…' : online ? 'online' : 'offline'}</p>\n"
        "      <input value={q} onChange={(e) => setQ(e.target.value)}\n"
        "             placeholder=\"Ask a question…\" style={{ width: '70%' }} />\n"
        "      <button onClick={ask} disabled={!q.trim()}>Ask</button>\n"
        "      {answer && <pre style={{ whiteSpace: 'pre-wrap' }}>{answer}</pre>}\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )


def compose_snippet(name: str, port: int) -> str:
    svc = name.replace("_", "-")
    return (
        f"# Add to docker-compose.yml (same network as `atria`). Then rebuild:\n"
        f"#   docker compose up -d --build {svc}\n"
        f"  {svc}:\n"
        f"    build:\n"
        f"      # Repo-root context so the image can install the shared atria_module_sdk.\n"
        f"      context: .\n"
        f"      dockerfile: modules/{name}/backend/Dockerfile\n"
        f"    ports:\n"
        f'      - "{port}:{port}"   # published so the browser can load remoteEntry.js\n'
        f"    environment:\n"
        f"      - MODULE_PUBLIC_BASE=http://localhost:{port}\n"
        f"    healthcheck:\n"
        f'      test: ["CMD", "python", "-c",\n'
        f'             "import urllib.request; urllib.request.urlopen(\'http://localhost:{port}/connector/health\')"]\n'
        f"      interval: 15s\n"
        f"      timeout: 5s\n"
        f"      retries: 5\n"
        f"      start_period: 30s\n"
        f"    restart: unless-stopped\n"
    )


_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="3" width="18" height="18" rx="3"/>'
    '<path d="M8 12h8M8 8h8M8 16h5"/></svg>\n'
)


def files(name: str, summary: str, port: int = 9300) -> dict[str, str]:
    """Return ``{relative_path: content}`` for a full service-module scaffold."""
    return {
        "SKILL.md": skill_md(name, summary),
        "manifest.json": manifest_json(name, port),
        "icon.svg": _ICON_SVG,
        "backend/app.py": backend_app_py(name),
        "backend/service.py": backend_service_py(name),
        "backend/requirements.txt": backend_requirements(),
        "backend/Dockerfile": backend_dockerfile(name, port),
        "frontend/package.json": frontend_package_json(name),
        "frontend/vite.config.ts": frontend_vite_config(name, port),
        "frontend/tsconfig.json": frontend_tsconfig(),
        "frontend/index.html": frontend_index_html(name),
        "frontend/src/DashboardApp.tsx": frontend_dashboard_tsx(name),
        "docker-compose.snippet.yml": compose_snippet(name, port),
    }
