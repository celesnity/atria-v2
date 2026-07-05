import json

from vetc_config import VetcConfig, load_vetc_config
from vetc_client import VetcClient, VetcError


def _cfg() -> VetcConfig:
    return VetcConfig(
        base_url="https://uat/partner-gateway/v1",
        client_id="cid",
        client_secret="sec",
        terminal_id="com.vetc.charging",
        mini_app_id="mid",
    )


class FakeTransport:
    """Records calls and replays a canned (status, json) per (method, url-fragment)."""

    def __init__(self, routes):
        self.calls = []
        self.routes = routes

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        for (m, frag), resp in self.routes.items():
            if method == m and frag in url:
                return resp
        return (404, {})


def test_config_unconfigured_without_credentials():
    assert load_vetc_config({}).configured is False
    assert load_vetc_config({"VETC_CLIENT_ID": "a", "VETC_CLIENT_SECRET": "b"}).configured is True


def test_config_env_selects_prod():
    cfg = load_vetc_config({"VETC_ENV": "prod", "VETC_CLIENT_ID": "a", "VETC_CLIENT_SECRET": "b"})
    assert cfg.base_url == "https://apigw-kds.vetc.com.vn/partner-gateway/v1"


def test_backend_token_success_and_cached():
    ft = FakeTransport(
        {("POST", "/auth/token"): (200, {"access_token": "tok", "expires_in": 3600})}
    )
    c = VetcClient(_cfg(), transport=ft, now=lambda: 1000.0)
    assert c.backend_token() == "tok"
    assert c.backend_token() == "tok"  # second call served from cache
    auth_calls = [x for x in ft.calls if "/auth/token" in x[1]]
    assert len(auth_calls) == 1
    body = auth_calls[0][3].decode()
    assert "grant_type=client_credentials" in body and "client_id=cid" in body


def test_auth_failure_raises():
    ft = FakeTransport(
        {
            ("POST", "/auth/token"): (
                401,
                {"error": "invalid_client", "error_description": "bad creds"},
            )
        }
    )
    try:
        VetcClient(_cfg(), transport=ft).backend_token()
        assert False, "expected VetcError"
    except VetcError as exc:
        assert "auth failed" in str(exc)


def test_init_payment_builds_request_and_parses_provider_payload():
    sample = {
        "code": "00",
        "message": "Success",
        "data": {
            "id": "i240dmojrufq5kiassfx",
            "order_id": "ORD1",
            "amount": 100000,
            "status": "CREATED",
            "provider_payload": {"hmac": "INIT_TRANS|...", "signature": "SIG=="},
        },
    }
    ft = FakeTransport(
        {
            ("POST", "/auth/token"): (200, {"access_token": "tok", "expires_in": 3600}),
            ("POST", "/mini-app/payments"): (201, sample),
        }
    )
    c = VetcClient(_cfg(), transport=ft, now=lambda: 1000.0)
    data = c.init_payment(
        "ORD1",
        100000,
        "gia hạn bảo hiểm",
        {
            "provider_name": "VETC",
            "service_name": "Bảo hiểm TNDS",
            "product_code": "SVC001",
            "product_name": "Bảo hiểm TNDS",
            "merchant_service": "vetc_copilot",
        },
        idempotency_key="ORD1",
    )
    assert data["status"] == "CREATED"
    assert data["provider_payload"]["signature"] == "SIG=="
    _, _, headers, body = [x for x in ft.calls if "/mini-app/payments" in x[1]][0]
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Idempotency-Key"] == "ORD1"
    sent = json.loads(body)
    assert sent["terminal_id"] == "com.vetc.charging"
    assert sent["order_id"] == "ORD1" and sent["amount"] == 100000


def test_get_user_info_parses_profile():
    ft = FakeTransport(
        {
            ("GET", "/mini-app/user"): (
                200,
                {"code": "00", "data": {"name": "Nguyễn A", "phone_number": "0987"}},
            )
        }
    )
    info = VetcClient(_cfg(), transport=ft).get_user_info("utok")
    assert info["name"] == "Nguyễn A"
