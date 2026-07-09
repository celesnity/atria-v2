from ipn_sig import ipn_sign, ipn_verify


def test_sign_then_verify_roundtrips():
    sig = ipn_sign("ORD1", "PAY1", "SUCCESS", "s3cret")
    assert ipn_verify("ORD1", "PAY1", "SUCCESS", sig, "s3cret") is True


def test_verify_rejects_tampering():
    sig = ipn_sign("ORD1", "PAY1", "SUCCESS", "s3cret")
    assert ipn_verify("ORD1", "PAY1", "FAILED", sig, "s3cret") is False
    assert ipn_verify("ORD2", "PAY1", "SUCCESS", sig, "s3cret") is False
    assert ipn_verify("ORD1", "PAY1", "SUCCESS", sig, "wrong") is False
    assert ipn_verify("ORD1", "PAY1", "SUCCESS", "deadbeef", "s3cret") is False
