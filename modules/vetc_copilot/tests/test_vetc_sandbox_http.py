import vetc_sandbox


def test_default_poster_posts_json(monkeypatch):
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def _fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["data"] = req.data
        seen["ctype"] = req.headers.get("Content-type")
        return _Resp()

    monkeypatch.setattr(vetc_sandbox.urllib.request, "urlopen", _fake_urlopen)
    vetc_sandbox.default_poster("http://ipn/cb", {"order_id": "ORD1", "status": "SUCCESS"})
    assert seen["url"] == "http://ipn/cb"
    assert b"ORD1" in seen["data"] and seen["ctype"] == "application/json"


def test_serve_is_callable():
    assert callable(vetc_sandbox.serve)
