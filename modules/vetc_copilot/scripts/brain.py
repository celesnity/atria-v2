"""Brain: rule-based service recommendation + grounded Q&A (LLM optional)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radar import deadlines_for_vehicle  # type: ignore[import-not-found]
from retriever import Retriever  # type: ignore[import-not-found]
from guardrails import (  # type: ignore[import-not-found]
    ADVISORY_NOTE,
    PRIVACY_NOTE,
    enforce_citations,
)

_UNCOVERED = "Thông tin này chưa có trong cơ sở tri thức. Vui lòng kiểm tra lại với VETC."


def _int(val: str, default: int = 0) -> int:
    try:
        return int(float(str(val)))
    except (TypeError, ValueError):
        return default


def recommend(ds, user_id: str, today: date) -> list[dict]:
    """Return ranked service recommendations for a user's primary vehicle.

    Rules are derived from each vehicle's state; every recommendation carries a
    human ``reason`` and the ``trigger`` that fired it.
    """
    vehicles = ds.vehicles_for_user(user_id)
    if not vehicles:
        return []
    v = vehicles[0]
    svc = {s["service_id"]: s.get("service_name", s["service_id"]) for s in ds.services}
    recs: list[dict] = []

    def add(sid: str, reason: str, trigger: str) -> None:
        if sid in svc:
            recs.append(
                {"service_id": sid, "service_name": svc[sid], "reason": reason, "trigger": trigger}
            )

    deadlines = {d["kind"]: d for d in deadlines_for_vehicle(v, today)}
    ins = deadlines.get("insurance")
    if ins and ins["days_to_expiry"] is not None and ins["days_to_expiry"] <= 30:
        add(
            "SVC001",
            f"Bảo hiểm TNDS sắp hết hạn ({ins['days_to_expiry']} ngày).",
            "insurance_expiring",
        )
    if (
        _int(v.get("vehicle_age_years")) > 7
        and str(v.get("roadside_assistance_status", "")).lower() == "inactive"
    ):
        add("SVC002", "Xe trên 7 năm và chưa kích hoạt cứu hộ.", "old_vehicle_no_roadside")
    insp = deadlines.get("inspection")
    if insp and insp["days_to_expiry"] is not None and insp["days_to_expiry"] <= 30:
        add("SVC003", f"Đăng kiểm sắp hết hạn ({insp['days_to_expiry']} ngày).", "inspection_due")
    if str(v.get("fuel_type", "")).lower() in {"ev", "electric", "điện"}:
        add("SVC005", "Xe điện — gợi ý trạm sạc.", "ev_owner")
    return recs


def _template_answer(hits: list[dict]) -> str:
    """Compose a deterministic cited answer from retrieved knowledge rows.

    Each row becomes one sentence ending with its citation BEFORE the period,
    so ``guardrails.enforce_citations`` (which splits on sentence punctuation)
    keeps the content instead of dropping it as an uncited sentence.
    """
    parts = []
    for h in hits:
        text = str(h.get("answer") or h.get("question")).rstrip(". ")
        parts.append(f"{text} [{h['knowledge_id']}].")
    return " ".join(parts)


def _llm_answer(question: str, hits: list[dict], client) -> str:
    passages = "\n".join(
        f"[{h['knowledge_id']}] {h.get('answer') or h.get('question')}" for h in hits
    )
    system = (
        "Bạn trả lời câu hỏi về sở hữu xe CHỈ dựa trên các đoạn được cung cấp. "
        "Trích dẫn mọi câu bằng thẻ trong ngoặc vuông, ví dụ [K001]. "
        "Không dùng kiến thức ngoài. Nếu không đủ thông tin, nói rõ."
    )
    user = f"Câu hỏi: {question}\n\nĐoạn tham chiếu:\n{passages}"
    return client.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])


def ask(ds, user_id: str, question: str, today: date, client=None) -> dict:
    """Answer a question grounded in the knowledge base, citing knowledge ids.

    Uses the LLM when ``client`` is available; otherwise a deterministic
    template. Abstains (``needs_review=True``) when nothing is retrieved.
    """
    hits = Retriever(ds.knowledge).search(question, k=3)
    if not hits:
        return {
            "answer": _UNCOVERED,
            "citations": [],
            "grounded": [],
            "needs_review": True,
            "source": "offline",
            "advisory": ADVISORY_NOTE,
            "privacy_note": PRIVACY_NOTE,
        }
    allowed = {h["knowledge_id"] for h in hits}
    if client is not None and getattr(client, "available", False):
        raw, source = _llm_answer(question, hits, client), "llm"
    else:
        raw, source = _template_answer(hits), "offline"
    checked = enforce_citations(raw, allowed)
    return {
        "answer": checked["answer"] or _UNCOVERED,
        "citations": checked["grounded"],
        "grounded": checked["grounded"],
        "needs_review": not checked["grounded"],
        "source": source,
        "advisory": ADVISORY_NOTE,
        "privacy_note": PRIVACY_NOTE,
    }
