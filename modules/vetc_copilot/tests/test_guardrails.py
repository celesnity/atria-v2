from guardrails import enforce_citations, consent_gate, privacy_refusal


def test_enforce_citations_drops_uncited():
    raw = "Đăng kiểm cần thiết [K001]. Tôi nghĩ bạn nên mua thêm bảo hiểm."
    out = enforce_citations(raw, {"K001"})
    assert "[K001]" in out["answer"]
    assert "Tôi nghĩ" not in out["answer"]
    assert out["dropped"]


def test_enforce_citations_keeps_inline_decimals():
    raw = "Phí bảo hiểm bắt buộc là 1.500.000 đồng mỗi năm [K001]."
    out = enforce_citations(raw, {"K001"})
    assert "1.500.000" in out["answer"]
    assert "[K001]" in out["answer"]
    assert out["dropped"] is False


def test_consent_gate_blocks_without_consent():
    assert consent_gate(True)[0] is True
    ok, reason = consent_gate(False)
    assert ok is False and reason


def test_privacy_refusal_on_cross_user():
    assert privacy_refusal("U001", "U002") is not None
    assert privacy_refusal("U001", "U001") is None
