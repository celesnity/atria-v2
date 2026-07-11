"""The generic module-connector passthrough (replaces the old maintenance route).

Every service module reaches its connector through this one auth-checked proxy;
core has no per-module routes.
"""
from __future__ import annotations

import atria.web.routes.module_connector as mc


def test_principal_of_maps_user_object():
    class _User:
        username = "eng@x"
        email = "eng@x.com"

    p = mc._principal_of(_User())
    assert p["username"] == "eng@x"
    assert p["email"] == "eng@x.com"


def test_principal_of_dict_and_unknown():
    assert mc._principal_of({"username": "u"})["username"] == "u"
    assert mc._principal_of(object())["username"] == "unknown"


def test_connector_for_missing_module(monkeypatch):
    import fastapi

    class _Reg:
        def connector(self, name):
            return None

        def get(self, name):
            raise KeyError(name)

    monkeypatch.setattr(mc, "get_registry", lambda: _Reg())
    try:
        mc._connector_for("nope")
        assert False, "expected HTTPException"
    except fastapi.HTTPException as exc:
        assert exc.status_code == 404


def test_connector_for_non_service_module(monkeypatch):
    import fastapi

    class _Mod:
        manifest = type("M", (), {"service": None})()

    class _Reg:
        def connector(self, name):
            return None

        def get(self, name):
            return _Mod()

    monkeypatch.setattr(mc, "get_registry", lambda: _Reg())
    try:
        mc._connector_for("plain")
        assert False, "expected HTTPException"
    except fastapi.HTTPException as exc:
        assert exc.status_code == 400


def test_connector_for_prefers_runtime_record(monkeypatch):
    """A self-registered module resolves from its connector record even when the
    on-disk guidance manifest has no static ``service`` block (the announce path)."""

    rec = type("Rec", (), {"connector_url": "http://module-template-web:9300"})()

    class _Reg:
        def connector(self, name):
            return rec

        def get(self, name):  # pragma: no cover - must not be consulted
            raise AssertionError("should not fall back to guidance manifest")

    monkeypatch.setattr(mc, "get_registry", lambda: _Reg())
    conn = mc._connector_for("module_template")
    assert conn.base_url == "http://module-template-web:9300"
    # Default health path is the standard connector contract endpoint.
    assert conn.health_path == "/connector/health"
