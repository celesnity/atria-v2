from atria.core.modules import remote
from atria.core.skill_tools import SkillToolContext


class _Conn:
    name = "mc"
    def __init__(self, resp):
        self._resp = resp
    def call_tool(self, tool, kwargs, **kw):
        return self._resp


def _ctx_with_capture():
    ctx = SkillToolContext()
    pushed = []
    ctx.push_block = lambda descriptor, module: pushed.append((descriptor, module))
    return ctx, pushed


def test_handler_forwards_blocks_to_push_block(monkeypatch):
    ctx, pushed = _ctx_with_capture()
    block = {"render": "remote", "remote_name": "mc", "component": "./X",
             "remote_entry": "http://h/dashboard/remoteEntry.js", "props": {"a": 1},
             "api_base": "http://h", "height": "auto", "title": None}
    conn = _Conn({"success": True, "output": "ok", "blocks": [block]})
    handler = remote._make_handler(ctx, conn, "mc_query")
    handler(query="hi")
    assert pushed == [(block, "mc")]


def test_handler_ignores_blocks_without_remote_entry(monkeypatch):
    ctx, pushed = _ctx_with_capture()
    conn = _Conn({"success": True, "output": "ok",
                  "blocks": [{"remote_name": "mc", "component": "./X"}]})  # no remote_entry
    handler = remote._make_handler(ctx, conn, "mc_query")
    handler(query="hi")
    assert pushed == []


def test_card_only_response_pushes_no_block():
    ctx, pushed = _ctx_with_capture()
    conn = _Conn({"success": True, "output": "ok", "card": {"answer": "a"}})
    handler = remote._make_handler(ctx, conn, "mc_query")
    handler(query="hi")
    assert pushed == []
