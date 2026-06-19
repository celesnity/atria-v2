"""Project workspace layout + JSON-backed metadata stores.

Implements the PRD's conceptual model:
    User → Project → { Datasets, Artifacts, Charts, Execution Traces, Conversation }

On disk under data/projects/<slug>/ :
    project.json          — id, name, description, created_at
    datasets/<id>.json    — dataset metadata + column profile
    datasets/<id>.parquet — parquet copy of the source file (FR-DS-03)
    datasets/raw/         — original CSV/XLSX kept for traceability
    artifacts/<id>.json   — artifact metadata
    artifacts/<id>.parquet — result table the artifact represents
    charts/<id>.json      — chart spec + link to source artifact
    traces/<id>.json      — full execution trace for one user query
    conversation.jsonl    — the single Project conversation (FR-PROJ-02)

JSON-only on purpose — keeps the module dependency-light. A future
migration to PostgreSQL is a drop-in (only the io functions change).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _resolve_projects_dir() -> Path:
    """Storage root precedence — keeps each chat session's data isolated.

    1. $ATRIA_DA_ROOT          — explicit override, wins everything.
    2. $ATRIA_WORKSPACE        — chat session's working directory.
    3. $ATRIA_SESSION_DIR      — fallback name some hosts use.
    4. CWD/.data_analysis      — last resort: scope to the current shell CWD.

    The module's own data/ folder is NEVER written to (it ships sample
    inputs only). All project workspaces live next to the conversation
    so they survive across sessions of the same chat, but stay isolated
    from other conversations.
    """
    env = os.environ.get("ATRIA_DA_ROOT")
    if env:
        return Path(env).expanduser() / "projects"
    ws = os.environ.get("ATRIA_WORKSPACE") or os.environ.get("ATRIA_SESSION_DIR")
    if ws:
        return Path(ws).expanduser() / ".data_analysis" / "projects"
    return Path.cwd() / ".data_analysis" / "projects"


PROJECTS_DIR = _resolve_projects_dir()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str = "") -> str:
    s = uuid.uuid4().hex[:12]
    return f"{prefix}{s}" if prefix else s


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    return re.sub(r"-+", "-", s).strip("-") or "project"


# ─── Filesystem layout ───────────────────────────────────────────────────

def project_root(slug: str) -> Path:
    return PROJECTS_DIR / slug


def ensure_project_dirs(slug: str) -> dict[str, Path]:
    base = project_root(slug)
    layout = {
        "base": base,
        "datasets": base / "datasets",
        "datasets_raw": base / "datasets" / "raw",
        "artifacts": base / "artifacts",
        "charts": base / "charts",
        "traces": base / "traces",
    }
    for p in layout.values():
        p.mkdir(parents=True, exist_ok=True)
    return layout


def warehouse_path(slug: str) -> Path:
    """Persistent DuckDB file for this project (catalog of all datasets)."""
    return project_root(slug) / "warehouse.duckdb"


# ─── Generic JSON I/O ────────────────────────────────────────────────────

def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Project CRUD ────────────────────────────────────────────────────────

def list_projects() -> list[dict[str, Any]]:
    if not PROJECTS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(PROJECTS_DIR.iterdir()):
        meta = read_json(p / "project.json")
        if meta:
            out.append(meta)
    return out


def create_project(name: str, description: str = "") -> dict[str, Any]:
    slug = slugify(name)
    base = project_root(slug)
    if base.exists() and (base / "project.json").exists():
        raise SystemExit(f"ERROR: project already exists: {slug}")
    ensure_project_dirs(slug)
    meta = {
        "id": new_id(),
        "slug": slug,
        "name": name,
        "description": description,
        "created_at": now(),
        "updated_at": now(),
    }
    write_json(base / "project.json", meta)
    # Initialise the single Conversation (FR-PROJ-02).
    (base / "conversation.jsonl").touch()
    _rebuild_index()
    return meta


def get_project(slug: str) -> dict[str, Any] | None:
    return read_json(project_root(slug) / "project.json")


def require_project(slug: str) -> dict[str, Any]:
    meta = get_project(slug)
    if meta is None:
        raise SystemExit(f"ERROR: project not found: {slug}")
    ensure_project_dirs(slug)
    return meta


def touch_project(slug: str) -> None:
    p = project_root(slug) / "project.json"
    meta = read_json(p)
    if meta is None:
        return
    meta["updated_at"] = now()
    write_json(p, meta)
    _rebuild_index()


def _rebuild_index() -> None:
    """Write data/projects/index.json — flat catalog the dashboard can fetch."""
    out: list[dict[str, Any]] = []
    if PROJECTS_DIR.exists():
        for p in sorted(PROJECTS_DIR.iterdir()):
            if not p.is_dir():
                continue
            meta = read_json(p / "project.json")
            if not meta:
                continue
            out.append({
                "id": meta.get("id"),
                "slug": meta.get("slug"),
                "name": meta.get("name"),
                "updated_at": meta.get("updated_at"),
                "counts": {
                    "datasets": len(list((p / "datasets").glob("*.json"))) if (p / "datasets").exists() else 0,
                    "artifacts": len(list((p / "artifacts").glob("*.json"))) if (p / "artifacts").exists() else 0,
                    "charts": len(list((p / "charts").glob("*.json"))) if (p / "charts").exists() else 0,
                    "traces": len(list((p / "traces").glob("*.json"))) if (p / "traces").exists() else 0,
                },
                "datasets": [read_json(f) for f in sorted((p / "datasets").glob("*.json"))] if (p / "datasets").exists() else [],
                "artifacts": [read_json(f) for f in sorted((p / "artifacts").glob("*.json"))] if (p / "artifacts").exists() else [],
                "charts": [read_json(f) for f in sorted((p / "charts").glob("*.json"))] if (p / "charts").exists() else [],
                "traces": [read_json(f) for f in sorted((p / "traces").glob("*.json"))] if (p / "traces").exists() else [],
            })
    write_json(PROJECTS_DIR / "index.json", {"projects": out, "updated_at": now()})


# ─── Dataset metadata store ──────────────────────────────────────────────

def list_datasets(slug: str) -> list[dict[str, Any]]:
    d = project_root(slug) / "datasets"
    if not d.exists():
        return []
    return [read_json(p) for p in sorted(d.glob("*.json")) if p.is_file()]


def save_dataset(slug: str, meta: dict[str, Any]) -> Path:
    p = project_root(slug) / "datasets" / f"{meta['id']}.json"
    write_json(p, meta)
    touch_project(slug)
    return p


def get_dataset(slug: str, dataset_id: str) -> dict[str, Any] | None:
    p = project_root(slug) / "datasets" / f"{dataset_id}.json"
    return read_json(p)


# ─── Artifact store ──────────────────────────────────────────────────────

def list_artifacts(slug: str) -> list[dict[str, Any]]:
    d = project_root(slug) / "artifacts"
    if not d.exists():
        return []
    return [read_json(p) for p in sorted(d.glob("*.json")) if p.is_file()]


def save_artifact(slug: str, meta: dict[str, Any]) -> Path:
    p = project_root(slug) / "artifacts" / f"{meta['id']}.json"
    write_json(p, meta)
    touch_project(slug)
    return p


def get_artifact(slug: str, artifact_id: str) -> dict[str, Any] | None:
    p = project_root(slug) / "artifacts" / f"{artifact_id}.json"
    return read_json(p)


# ─── Chart store ─────────────────────────────────────────────────────────

def list_charts(slug: str) -> list[dict[str, Any]]:
    d = project_root(slug) / "charts"
    if not d.exists():
        return []
    return [read_json(p) for p in sorted(d.glob("*.json")) if p.is_file()]


def save_chart(slug: str, meta: dict[str, Any]) -> Path:
    p = project_root(slug) / "charts" / f"{meta['id']}.json"
    write_json(p, meta)
    touch_project(slug)
    return p


def get_chart(slug: str, chart_id: str) -> dict[str, Any] | None:
    p = project_root(slug) / "charts" / f"{chart_id}.json"
    return read_json(p)


# ─── Execution traces ────────────────────────────────────────────────────

def list_traces(slug: str) -> list[dict[str, Any]]:
    d = project_root(slug) / "traces"
    if not d.exists():
        return []
    return [read_json(p) for p in sorted(d.glob("*.json")) if p.is_file()]


def save_trace(slug: str, trace: dict[str, Any]) -> Path:
    p = project_root(slug) / "traces" / f"{trace['id']}.json"
    write_json(p, trace)
    touch_project(slug)
    return p


# ─── Conversation (the single per-project conversation) ─────────────────

def conversation_path(slug: str) -> Path:
    return project_root(slug) / "conversation.jsonl"


def append_message(slug: str, role: str, content: str, meta: dict[str, Any] | None = None) -> None:
    p = conversation_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now(), "role": role, "content": content, "meta": meta or {}}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_conversation(slug: str, limit: int | None = None) -> list[dict[str, Any]]:
    p = conversation_path(slug)
    if not p.exists():
        return []
    msgs = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return msgs[-limit:] if limit else msgs
