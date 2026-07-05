from config import load_brain_config
from client import BrainClient


def test_config_env_override_and_openai_key_fallback():
    cfg = load_brain_config({"OPENAI_API_KEY": "sk-x", "VA_BRAIN_MODEL": "gpt-4o-mini"})
    assert cfg.api_key == "sk-x"
    assert cfg.model == "gpt-4o-mini"


def test_client_unavailable_without_key():
    cfg = load_brain_config({})
    assert BrainClient(cfg).available is False


def test_client_chat_uses_injected_factory():
    cfg = load_brain_config({"OPENAI_API_KEY": "sk-x"})

    class _Resp:
        choices = [type("C", (), {"message": type("M", (), {"content": "hi"})})]

    class _Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    return _Resp()

    bc = BrainClient(cfg, client_factory=lambda b, k: _Fake())
    assert bc.chat([{"role": "user", "content": "x"}]) == "hi"
