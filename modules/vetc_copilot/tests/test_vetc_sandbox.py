import json
import urllib.parse

from vetc_sandbox import new_state, handle

ENV = {
    "SANDBOX_CLIENT_ID": "cid",
    "SANDBOX_CLIENT_SECRET": "sec",
    "SANDBOX_HMAC_SECRET": "hmac",
    "SANDBOX_USERS": json.dumps({"U001": {"name": "Nguyễn A", "phone_number": "0987"}}),
}


def _form(d):
    return urllib.parse.urlencode(d).encode()


def _noop_poster(url, payload):
    return None


def test_backend_token_ok_and_bad_credentials():
    st = new_state(ENV)
    code, data = handle(
        "POST", "/partner-gateway/v1/auth/token", {}, _form(
            {"grant_type": "client_credentials", "client_id": "cid", "client_secret": "sec"}), st, _noop_poster)
    assert code == 200 and data["token_type"] == "Bearer" and data["access_token"]
    code2, data2 = handle(
        "POST", "/partner-gateway/v1/auth/token", {}, _form(
            {"grant_type": "client_credentials", "client_id": "cid", "client_secret": "WRONG"}), st, _noop_poster)
    assert code2 == 401 and data2["error"] == "invalid_client"


def test_authcode_exchange_and_user_info():
    st = new_state(ENV)
    _, ac = handle("POST", "/sandbox/authcode", {}, json.dumps({"user_id": "U001"}).encode(), st, _noop_poster)
    code, tok = handle(
        "POST", "/partner-gateway/v1/mini-app/token", {}, _form(
            {"grant_type": "authorization_code", "client_id": "cid", "client_secret": "sec",
             "code": ac["auth_code"]}), st, _noop_poster)
    assert code == 200 and tok["access_token"]
    ucode, uinfo = handle(
        "GET", "/partner-gateway/v1/mini-app/user",
        {"Authorization": f"Bearer {tok['access_token']}"}, b"", st, _noop_poster)
    assert ucode == 200 and uinfo["data"]["name"] == "Nguyễn A"


def test_user_info_rejects_bad_token():
    st = new_state(ENV)
    code, data = handle(
        "GET", "/partner-gateway/v1/mini-app/user", {"Authorization": "Bearer nope"}, b"", st, _noop_poster)
    assert code == 401 and data["code"] == "UNAUTHORIZED"
