import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("VETC_E2E") != "1", reason="set VETC_E2E=1 with the sandbox running")


def test_sandbox_auth_and_payment_ipn(tmp_path, monkeypatch):
    # Requires: vetc-sandbox reachable at VETC_BASE_URL, VETC_IPN_URL -> a running /ipn.
    from vetc_config import load_vetc_config
    from vetc_client import VetcClient

    cfg = load_vetc_config()
    assert cfg.configured, "VETC_CLIENT_ID/SECRET must be set to the sandbox values"
    client = VetcClient(cfg)
    assert client.backend_token()  # real HTTP round-trip to the sandbox
    data = client.init_payment(
        "ORD-E2E", 100000, "e2e", {"provider_name": "VETC", "service_name": "TNDS",
        "product_code": "SVC001", "product_name": "TNDS", "merchant_service": "vetc_copilot",
        "ipn_url": os.environ["VETC_IPN_URL"]}, idempotency_key="ORD-E2E")
    assert data["status"] == "CREATED" and data["provider_payload"]["signature"]
