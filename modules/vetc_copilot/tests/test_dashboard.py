from pathlib import Path


def test_dashboard_is_self_contained_and_branded():
    html = (Path(__file__).resolve().parent.parent / "dashboard.html").read_text(encoding="utf-8")
    assert "/api/radar" in html          # wired to the serve routes
    assert "/api/renew" in html
    assert "#2D44E0" in html             # cobalt brand color
    assert "http://" not in html.replace("http://localhost", "").replace("http://127.0.0.1", "")
