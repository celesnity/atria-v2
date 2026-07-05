from pathlib import Path


def test_dashboard_is_self_contained_and_branded():
    html = (Path(__file__).resolve().parent.parent / "dashboard.html").read_text(encoding="utf-8")
    assert "/api/radar" in html  # standalone-serve fallback route
    assert "/api/renew" in html
    assert "#2D44E0" in html  # cobalt brand color
    assert "http://" not in html.replace("http://localhost", "").replace("http://127.0.0.1", "")


def test_dashboard_uses_atria_bridge():
    """Inside Atria the dashboard must reach the backend via the AtriaDash bridge
    (runs autopilot.py as a subprocess), with a fetch fallback for standalone serve."""
    html = (Path(__file__).resolve().parent.parent / "dashboard.html").read_text(encoding="utf-8")
    assert "__bridge.js" in html  # loads the Atria bridge
    assert "AtriaDash" in html  # uses window.AtriaDash
    assert "autopilot.py" in html  # bridge runs the module CLI
    # every endpoint the UI needs must be routed through the bridge/fallback layer
    for cmd in ("radar", "recommend", "ask", "wallet", "renew"):
        assert cmd in html
