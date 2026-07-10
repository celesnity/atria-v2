import httpx
from atria_module_sdk.announce import AnnounceConfig
from atria_module_sdk.client import AtriaClient, AtriaClientError


def _client(handler):
    cfg = AnnounceConfig(atria_url="http://atria:8000", connector_url="http://m:9300",
                         remote_entry="http://m:9300/dashboard/remoteEntry.js")
    c = AtriaClient("m", cfg)
    # inject a mock transport by monkeypatching httpx.post used inside _post
    return c, cfg


def test_push_block_posts_expected_payload(monkeypatch):
    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url; captured["json"] = json
        return httpx.Response(200, json={"block_id": "b1"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("atria_module_sdk.client.httpx.post", fake_post)
    c, _ = _client(None)
    bid = c.push_block("sess", "./Job", {"pct": 0})
    assert bid == "b1"
    assert captured["url"] == "http://atria:8000/api/blocks/remote/push"
    assert captured["json"]["remote_name"] == "m"
    assert captured["json"]["api_base"] == "http://m:9300"


def test_push_error_raises(monkeypatch):
    def fake_post(url, json, headers, timeout):
        return httpx.Response(500, request=httpx.Request("POST", url))
    monkeypatch.setattr("atria_module_sdk.client.httpx.post", fake_post)
    c, _ = _client(None)
    import pytest
    with pytest.raises(AtriaClientError):
        c.update_block("sess", "b1", {"pct": 9})
