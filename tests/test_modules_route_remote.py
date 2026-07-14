"""The modules API serializes the manifest `remote` block for the web-ui."""
from __future__ import annotations

from minder.core.modules.store import (
    Module, ModuleManifest, ModuleRemoteManifest,
)
from minder.web.routes.modules import ModuleManifestOut, ModuleOut


def test_module_out_serializes_remote_block(tmp_path):
    manifest = ModuleManifest(
        display_name="Maintenance Copilot",
        remote=ModuleRemoteManifest(
            name="maintenance_copilot",
            remote_entry="http://localhost:9200/dashboard/remoteEntry.js",
            exposed={"dashboard": "./Dashboard"},
        ),
    )
    m = Module(name="maintenance_copilot", skill_md="x", dir=tmp_path, mtime=0.0,
               files=[], manifest=manifest)
    out = ModuleOut.model_validate(m)
    assert out.manifest is not None
    assert out.manifest.remote is not None
    assert out.manifest.remote.remote_entry == "http://localhost:9200/dashboard/remoteEntry.js"
    assert out.manifest.remote.exposed["dashboard"] == "./Dashboard"


def test_module_out_no_remote_is_none(tmp_path):
    m = Module(name="plain", skill_md="x", dir=tmp_path, mtime=0.0, files=[],
               manifest=ModuleManifest(display_name="Plain"))
    out = ModuleOut.model_validate(m)
    assert out.manifest.remote is None
