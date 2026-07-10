from atria.core.modules import remote
from atria.core.skill_tools import SkillToolContext


class _StreamConn:
    name = "m"
    def stream_tool(self, tool, arguments, timeout=300.0, **kwargs):
        yield {"event": "block", "block": {"remote_entry": "http://h/dashboard/x", "component": "./J"}}
        yield {"event": "final", "success": True, "output": "done"}
    def call_tool(self, *a, **k):
        return {"success": True, "output": "done"}


def test_stream_block_event_pushes_block():
    ctx = SkillToolContext()
    pushed = []
    ctx.push_block = lambda blk, module: pushed.append((blk, module))
    result = remote._run_stream(ctx, _StreamConn(), "t", {}, "q")
    assert pushed and pushed[0][1] == "m"
    assert result["output"] == "done"
