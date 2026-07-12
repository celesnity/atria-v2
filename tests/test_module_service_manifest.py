"""Manifest parsing for service-module `service`/`remote` blocks."""
from __future__ import annotations

import json
from pathlib import Path

from minder.core.modules import store


def _write_module(tmp_path: Path) -> Path:
    d = tmp_path / "svcmod"
    d.mkdir()
    (d / "SKILL.md").write_text("---\ndescription: test\n---\nbody\n")
    (d / "manifest.json").write_text(json.dumps({
        "display_name": "Svc Mod",
        "service": {
            "connector_url": "http://svcmod:9200",
            "tools": [{"name": "svc_query", "description": "q", "parameters": {"type": "object"}}],
        },
        "remote": {
            "name": "svcmod",
            "remoteEntry": "http://localhost:9200/dashboard/remoteEntry.js",
            "exposed": {"dashboard": "./Dashboard"},
        },
    }))
    return d


def test_service_and_remote_blocks_parse(tmp_path):
    _write_module(tmp_path)
    m = store.read_module(tmp_path, "svcmod")
    assert m.manifest.service is not None
    assert m.manifest.service.connector_url == "http://svcmod:9200"
    assert m.manifest.service.health_path == "/connector/health"  # default
    assert m.manifest.service.tools[0]["name"] == "svc_query"
    assert m.manifest.remote.remote_entry == "http://localhost:9200/dashboard/remoteEntry.js"
    assert m.manifest.remote.exposed["dashboard"] == "./Dashboard"


def test_module_without_service_block_is_none(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "SKILL.md").write_text("---\ndescription: t\n---\nx\n")
    (d / "manifest.json").write_text(json.dumps({"display_name": "Plain"}))
    m = store.read_module(tmp_path, "plain")
    assert m.manifest.service is None
    assert m.manifest.remote is None


def test_service_without_connector_url_is_none(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("---\ndescription: t\n---\nx\n")
    (d / "manifest.json").write_text(json.dumps({
        "display_name": "Bad", "service": {"tools": []},  # missing connector_url
    }))
    m = store.read_module(tmp_path, "bad")
    assert m.manifest.service is None  # degrades to None, doesn't crash
