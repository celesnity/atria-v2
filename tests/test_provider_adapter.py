"""Tests for the ProviderAdapter ABC and AgentHttpClient."""

from unittest.mock import MagicMock

from atria.core.agents.components.api.base_adapter import ProviderAdapter
from atria.core.agents.components.api.http_client import AgentHttpClient
from atria.core.agents.components.api.configuration import create_http_client


class TestProviderAdapterABC:
    """AgentHttpClient is a ProviderAdapter."""

    def test_agent_http_client_is_provider_adapter(self):
        client = AgentHttpClient(
            api_url="http://localhost:8080/v1/chat/completions",
            headers={"Authorization": "Bearer test"},
        )
        assert isinstance(client, ProviderAdapter)


class TestAgentHttpClientPassthroughs:
    """convert_request and convert_response are passthroughs."""

    def test_convert_request_passthrough(self):
        client = AgentHttpClient(
            api_url="http://localhost:8080/v1/chat/completions",
            headers={"Authorization": "Bearer test"},
        )
        payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        result = client.convert_request(payload)
        assert result["model"] == "gpt-4"
        assert result["messages"] == payload["messages"]

    def test_convert_response_passthrough(self):
        client = AgentHttpClient(
            api_url="http://localhost:8080/v1/chat/completions",
            headers={"Authorization": "Bearer test"},
        )
        response = {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
        assert client.convert_response(response) is response

    def test_no_prompt_caching(self):
        client = AgentHttpClient(
            api_url="http://localhost:8080/v1/chat/completions",
            headers={"Authorization": "Bearer test"},
        )
        assert ProviderAdapter.supports_prompt_caching.fget(client) is False  # type: ignore[attr-defined]


class TestCreateHttpClient:
    """create_http_client always returns AgentHttpClient."""

    def test_returns_agent_http_client(self):
        config = MagicMock()
        config.api_base_url = None
        config.get_api_key.return_value = "test-key"

        client = create_http_client(config)
        assert isinstance(client, ProviderAdapter)
        assert isinstance(client, AgentHttpClient)

    def test_uses_custom_base_url(self):
        config = MagicMock()
        config.api_base_url = "http://localhost:11434/v1/chat/completions"
        config.get_api_key.return_value = "test-key"

        client = create_http_client(config)
        assert isinstance(client, AgentHttpClient)
        assert client._api_url == "http://localhost:11434/v1/chat/completions"

    def test_uses_default_openai_url(self):
        config = MagicMock()
        config.api_base_url = None
        config.get_api_key.return_value = "test-key"

        client = create_http_client(config)
        assert isinstance(client, AgentHttpClient)
        assert "openai.com" in client._api_url
