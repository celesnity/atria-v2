"""on_thinking must not synthesize word-chunks; one token then done."""

from minder.web.web_ui_callback import WebUICallback
from minder.web.protocol import WSMessageType


def _make_callback():
    cb = WebUICallback.__new__(WebUICallback)
    cb.session_id = "sess1"
    cb._sent = []
    cb._broadcast = lambda msg: cb._sent.append(msg)  # type: ignore[attr-defined]
    return cb


def test_on_thinking_emits_single_token_then_done():
    cb = _make_callback()
    content = " ".join(f"word{i}" for i in range(30))  # 30 words, >8

    cb.on_thinking(content)

    tokens = [m for m in cb._sent if m["type"] == WSMessageType.THINKING_TOKEN]
    dones = [m for m in cb._sent if m["type"] == WSMessageType.THINKING_DONE]
    assert len(tokens) == 1
    assert tokens[0]["data"]["token"] == content
    assert len(dones) == 1


def test_on_thinking_ignores_empty():
    cb = _make_callback()
    cb.on_thinking("   ")
    assert cb._sent == []
