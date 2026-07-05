from config import load_brain_config
from client import BrainClient


def test_config_env_override_and_openai_key_fallback():
    cfg = load_brain_config({"OPENAI_API_KEY": "sk-x", "VA_BRAIN_MODEL": "gpt-4o-mini"})
    assert cfg.api_key == "sk-x"
    assert cfg.model == "gpt-4o-mini"


def test_client_unavailable_without_key():
    cfg = load_brain_config({})
    assert BrainClient(cfg).available is False


def test_config_prefers_openrouter_key_and_defaults():
    cfg = load_brain_config({"OPENROUTER_API_KEY": "sk-or-abc"})
    assert cfg.api_key == "sk-or-abc"
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.model == "openai/gpt-oss-120b:free"
    assert cfg.provider == "openrouter"


def test_config_sk_or_key_in_openai_var_routes_to_openrouter():
    # An OpenRouter key stored in OPENAI_API_KEY must still use OpenRouter's endpoint.
    cfg = load_brain_config({"OPENAI_API_KEY": "sk-or-xyz"})
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.provider == "openrouter"


def test_config_va_brain_overrides_win():
    cfg = load_brain_config(
        {
            "OPENROUTER_API_KEY": "sk-or-abc",
            "VA_BRAIN_BASE_URL": "https://example.test/v1",
            "VA_BRAIN_MODEL": "custom-model",
        }
    )
    assert cfg.base_url == "https://example.test/v1"
    assert cfg.model == "custom-model"


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
