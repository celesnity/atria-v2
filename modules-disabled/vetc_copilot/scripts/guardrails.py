"""Trust guardrails: citation enforcement, advisory/privacy notes, consent."""

from __future__ import annotations

import re

ADVISORY_NOTE = (
    "Thông tin chỉ mang tính hỗ trợ, không phải tư vấn pháp lý hoặc tài chính ràng buộc."
)
PRIVACY_NOTE = (
    "Dữ liệu xe và giấy tờ chỉ dùng để nhắc hạn và hỗ trợ bạn; bạn có thể tắt bất cứ lúc nào."
)

_CITE = re.compile(r"\[([A-Za-z0-9_-]+)\]")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def enforce_citations(answer: str, allowed_ids: set[str]) -> dict:
    """Keep only sentences citing an allowed id; report what was dropped.

    Args:
        answer: Raw model answer.
        allowed_ids: Citation ids that were actually retrieved and sent.

    Returns:
        ``{"answer": kept_text, "grounded": [ids...], "dropped": bool}``.
    """
    kept: list[str] = []
    grounded: set[str] = set()
    dropped = False
    for sent in (s.strip() for s in _SENT_SPLIT.split(answer.strip()) if s.strip()):
        ids = {m for m in _CITE.findall(sent) if m in allowed_ids}
        if ids:
            kept.append(sent)
            grounded |= ids
        else:
            dropped = True
    return {"answer": " ".join(kept), "grounded": sorted(grounded), "dropped": dropped}


def consent_gate(consent: bool) -> tuple[bool, str]:
    """Return ``(ok, reason)``; a transaction requires explicit user consent."""
    if consent:
        return True, ""
    return False, "Cần bạn xác nhận đồng ý trước khi thực hiện giao dịch."


def privacy_refusal(requester_id: str, target_id: str) -> str | None:
    """Return a refusal message when accessing another user's data, else None."""
    if requester_id != target_id:
        return "Không thể truy cập dữ liệu của người dùng khác. " + PRIVACY_NOTE
    return None
