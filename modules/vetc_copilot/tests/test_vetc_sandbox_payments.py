import json

from vetc_sandbox import new_state, handle
from ipn_sig import ipn_verify

# autocomplete=-1 disables the background Timer so tests drive completion via /complete (deterministic, no dangling threads).
ENV = {"SANDBOX_CLIENT_ID": "cid", "SANDBOX_CLIENT_SECRET": "sec", "SANDBOX_HMAC_SECRET": "hmac",
       "SANDBOX_AUTOCOMPLETE_SECONDS": "-1"}


def _token(st):
    import urllib.parse
    _, d = handle("POST", "/partner-gateway/v1/auth/token", {}, urllib.parse.urlencode(
        {"client_id": "cid", "client_secret": "sec", "grant_type": "client_credentials"}).encode(),
        st, lambda u, p: None)
    return d["access_token"]


def _init(st, ipn_url, poster):
    tok = _token(st)
    body = json.dumps({
        "terminal_id": "com.vetc.charging", "order_id": "ORD1", "amount": 100000,
        "description": "gia hạn", "metadata": {"provider_name": "VETC", "service_name": "Bảo hiểm TNDS",
        "product_code": "SVC001", "product_name": "Bảo hiểm TNDS", "merchant_service": "vetc_copilot",
        "ipn_url": ipn_url}}).encode()
    return handle("POST", "/partner-gateway/v1/mini-app/payments",
                  {"Authorization": f"Bearer {tok}"}, body, st, poster)


def test_init_payment_returns_created_with_provider_payload():
    st = new_state(ENV)
    code, data = _init(st, "http://ipn", lambda u, p: None)
    assert code == 201 and data["code"] == "00"
    d = data["data"]
    assert d["status"] == "CREATED" and d["order_id"] == "ORD1"
    assert d["provider_payload"]["signature"] and d["provider_payload"]["hmac"]


def test_init_rejects_bad_backend_token():
    st = new_state(ENV)
    code, data = handle("POST", "/partner-gateway/v1/mini-app/payments",
                        {"Authorization": "Bearer nope"}, json.dumps({"order_id": "X", "amount": 1,
                        "terminal_id": "t", "metadata": {}}).encode(), st, lambda u, p: None)
    assert code == 401


def test_complete_fires_signed_ipn():
    st = new_state(ENV)
    sent = []
    _init(st, "http://ipn/cb", lambda u, p: sent.append((u, p)))
    pid = list(st.payments.keys())[0]
    code, _ = handle("POST", f"/partner-gateway/v1/mini-app/payments/{pid}/complete", {}, b"", st,
                     lambda u, p: sent.append((u, p)))
    assert code == 200
    assert st.payments[pid]["status"] == "SUCCESS"
    url, payload = sent[-1]
    assert url == "http://ipn/cb" and payload["status"] == "SUCCESS"
    assert ipn_verify(payload["order_id"], payload["payment_id"], "SUCCESS", payload["signature"], "hmac")
