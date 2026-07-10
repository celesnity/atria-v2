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


def test_push_artifact(monkeypatch):
    import base64
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(200, json={"artifact_id": 9},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("atria_module_sdk.client.httpx.post", fake_post)
    c, _ = _client(None)
    artifact_id = c.push_artifact("sess", "report.pdf", b"hello artifact")
    assert artifact_id == 9
    assert captured["url"] == "http://atria:8000/api/artifacts/remote/push"
    assert captured["json"]["session_id"] == "sess"
    assert captured["json"]["filename"] == "report.pdf"
    # Verify content was base64-encoded correctly
    assert base64.b64decode(captured["json"]["content_b64"]) == b"hello artifact"
    assert captured["json"]["type"] == "report"
