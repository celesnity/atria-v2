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
    for cmd in ("radar", "recommend", "agent", "wallet", "renew"):
        assert cmd in html


def test_dashboard_has_agentic_chat():
    """The assistant panel must be the agentic chat (calls the `agent` command)."""
    html = (Path(__file__).resolve().parent.parent / "dashboard.html").read_text(encoding="utf-8")
    assert "chat-log" in html
    assert "'agent'" in html  # callApi('agent', ...) drives the assistant
    assert "tool-chip" in html  # shows which tools the AI invoked


def test_dashboard_polls_wallet_for_pending_renewal():
    html = (Path(__file__).resolve().parent.parent / "dashboard.html").read_text(encoding="utf-8")
    assert "pending_user_confirmation" in html  # handles the async gateway path
    assert "pollWallet" in html  # polls /api/wallet until the policy appears
