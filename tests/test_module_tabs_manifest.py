"""Tests for the module dashboard `tabs` manifest field."""
from minder.core.modules.store import _parse_dashboard


def test_parse_dashboard_reads_tabs_with_entry_and_hash_mode():
    raw = {
        "title": "Plan board",
        "tabs": [
            {"id": "plan-board", "label": "Plan board", "entry": "dashboard.html"},
            {"id": "readiness", "label": "Readiness"},  # entry omitted -> hash mode
        ],
    }
    dash = _parse_dashboard(raw)
    assert dash is not None
    assert [t.id for t in dash.tabs] == ["plan-board", "readiness"]
    assert dash.tabs[0].entry == "dashboard.html"
    assert dash.tabs[1].entry is None


def test_parse_dashboard_defaults_tabs_to_empty_list():
    dash = _parse_dashboard({"title": "Legacy"})
    assert dash is not None
    assert dash.tabs == []


def test_parse_dashboard_drops_tabs_missing_id_or_label():
    raw = {"tabs": [{"label": "no id"}, {"id": "no-label"}, {"id": "ok", "label": "OK"}]}
    dash = _parse_dashboard(raw)
    assert [t.id for t in dash.tabs] == ["ok"]
