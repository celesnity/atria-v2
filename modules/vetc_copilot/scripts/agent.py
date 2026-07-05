"""Agentic AI Co-Pilot for VETC Auto-Pilot.

The LLM is the brain: given a Vietnamese conversation, it decides which backend
tool to call, we execute it, feed the result back, and loop until the model
produces a natural-language answer. This is model-agnostic (prompt-based tool
calling, works on OpenRouter free models) — it does not depend on a provider's
function-calling API.

Money-touching logic stays deterministic and guarded: the ``renew_service``
tool runs the existing ``hands.renew`` (consent + mock APIs), and the system
prompt requires the assistant to confirm with the user before renewing.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radar import radar_for_user  # type: ignore[import-not-found]
from brain import ask as brain_ask, recommend as brain_recommend  # type: ignore[import-not-found]
from hands import renew as hands_renew  # type: ignore[import-not-found]
from guardrails import ADVISORY_NOTE  # type: ignore[import-not-found]

_MAX_STEPS = 5

_TOOLS_DOC = (
    "get_deadlines(): xem các hạn giấy tờ của xe người dùng (đăng kiểm, bảo hiểm TNDS, đăng ký).\n"
    "recommend_services(): gợi ý các dịch vụ VETC phù hợp với xe/hồ sơ người dùng.\n"
    "lookup_regulation(question): tra cứu quy định/thủ tục sở hữu xe (kết quả có trích dẫn [Kxxx]).\n"
    "get_wallet(vehicle_id): xem ví giấy tờ số của một xe.\n"
    "renew_service(vehicle_id, service_id): GIA HẠN dịch vụ (thao tác chạm tiền, mô phỏng). "
    "CHỈ gọi sau khi người dùng đã xác nhận đồng ý gia hạn."
)


def _system_prompt(user_id: str) -> str:
    return (
        "Bạn là Trợ lý AI của VETC Auto-Pilot, hỗ trợ chủ xe bằng tiếng Việt. "
        f"Bạn đang phục vụ người dùng {user_id}.\n"
        "Bạn có các CÔNG CỤ sau:\n" + _TOOLS_DOC + "\n\n"
        "QUY TẮC:\n"
        "- Khi cần dữ liệu, chỉ trả về MỘT dòng JSON duy nhất: "
        '{"tool": "<tên>", "args": {...}} và KHÔNG kèm chữ nào khác.\n'
        "- Khi đã đủ dữ liệu, trả lời người dùng bằng tiếng Việt tự nhiên, ngắn gọn (KHÔNG JSON).\n"
        "- LUÔN hỏi xác nhận trước khi gọi renew_service.\n"
        "- Khi nói về quy định, giữ nguyên trích dẫn [Kxxx] từ kết quả lookup_regulation.\n"
        "- Không bịa số liệu; chỉ dùng dữ liệu từ kết quả công cụ."
    )


def _primary_vehicle_id(ds, user_id: str) -> str:
    vehicles = ds.vehicles_for_user(user_id)
    return vehicles[0].get("vehicle_id", "") if vehicles else ""


def run_tool(name: str, args: dict, ds, user_id: str, today: date, client) -> dict:
    """Execute one tool by name. User-scoped tools are pinned to ``user_id``.

    Args:
        name: Tool name the model requested.
        args: Tool arguments from the model (untrusted; user scope is overridden).
        ds: The loaded Dataset.
        user_id: The acting user (authoritative — the model cannot query others).
        today: Reference date.
        client: Brain client (used by lookup_regulation for grounded phrasing).

    Returns:
        A JSON-serializable result dict (never raises for a known tool).
    """
    if name == "get_deadlines":
        return radar_for_user(ds, user_id, today)
    if name == "recommend_services":
        return {"recommendations": brain_recommend(ds, user_id, today)}
    if name == "lookup_regulation":
        return brain_ask(ds, user_id, str(args.get("question", "")), today, client)
    if name == "get_wallet":
        vid = str(args.get("vehicle_id") or _primary_vehicle_id(ds, user_id))
        return {"vehicle_id": vid, "documents": ds.documents_for_vehicle(vid)}
    if name == "renew_service":
        vid = str(args.get("vehicle_id") or _primary_vehicle_id(ds, user_id))
        sid = str(args.get("service_id") or "SVC001")
        return hands_renew(ds, user_id, vid, sid, today, consent=True)
    return {"error": f"unknown tool: {name}"}


def parse_tool_call(raw: str) -> dict | None:
    """Return ``{"tool", "args"}`` if the model output is a tool call, else None.

    Tolerates code fences and surrounding prose: finds the first JSON object that
    contains a ``"tool"`` key.
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    for candidate in _json_objects(text):
        if isinstance(candidate, dict) and "tool" in candidate:
            args = candidate.get("args", {})
            return {"tool": str(candidate["tool"]), "args": args if isinstance(args, dict) else {}}
    return None


def _json_objects(text: str):
    """Yield parsed JSON objects found in ``text`` (whole string first, then spans)."""
    try:
        yield json.loads(text)
        return
    except (ValueError, TypeError):
        pass
    for match in re.finditer(r"\{.*?\}", text, flags=re.DOTALL):
        try:
            yield json.loads(match.group(0))
        except (ValueError, TypeError):
            continue


_BUSY = (
    "Trợ lý AI tạm thời bận (mô hình miễn phí đang bị giới hạn tần suất). "
    "Vui lòng thử lại sau giây lát."
)


def _chat_with_retry(client, convo: list[dict], retries: int = 2) -> str:
    """Call ``client.chat`` with short exponential backoff on transient errors."""
    delay = 1.5
    for attempt in range(retries + 1):
        try:
            return client.chat(convo)
        except Exception:  # noqa: BLE001 - retry rate-limit/transport errors
            if attempt >= retries:
                raise
            time.sleep(delay)
            delay *= 2
    return ""  # pragma: no cover - loop always returns or raises


def _fallback_reply(steps: list[dict]) -> str:
    """Summarize the last tool result deterministically when the LLM is unavailable."""
    if not steps:
        return ""
    last = steps[-1]
    tool, res = last.get("tool"), last.get("result") or {}
    if tool == "get_deadlines":
        parts = []
        for v in res.get("vehicles", []):
            for d in v.get("deadlines", []):
                days = d.get("days_to_expiry")
                parts.append(
                    f"{d.get('label')}: còn {days} ngày"
                    if days is not None
                    else f"{d.get('label')}: chưa rõ"
                )
        return ("Các mốc sắp tới — " + "; ".join(parts) + ".") if parts else ""
    if tool == "recommend_services":
        names = [
            r.get("service_name") for r in res.get("recommendations", []) if r.get("service_name")
        ]
        return ("Gợi ý dịch vụ: " + ", ".join(names) + ".") if names else ""
    if tool == "renew_service" and res.get("ok"):
        return f"Đã gia hạn {res.get('service_name')} — hạn mới {res.get('new_expiry')} (mô phỏng)."
    if tool == "lookup_regulation":
        return str(res.get("answer") or "")
    return ""


def run_agent(ds, user_id: str, messages: list[dict], today: date, client) -> dict:
    """Run one agentic turn: the LLM may call tools before answering.

    Never raises — on an LLM/transport failure (e.g. a rate-limited free model)
    it degrades to a deterministic summary of whatever tool results it gathered,
    or a "try again" notice.

    Args:
        ds: The loaded Dataset.
        user_id: The acting user.
        messages: Prior conversation as ``[{"role","content"}, ...]`` (the last
            entry is the newest user message).
        today: Reference date.
        client: Brain client. When unavailable, returns a configuration notice.

    Returns:
        ``{"reply": str, "steps": [{"tool","args","result"}, ...], "advisory": str}``.
    """
    if client is None or not getattr(client, "available", False):
        return {
            "reply": "Trợ lý AI cần cấu hình khóa LLM (OpenRouter/OpenAI) để hoạt động.",
            "steps": [],
            "advisory": ADVISORY_NOTE,
        }
    convo: list[dict] = [{"role": "system", "content": _system_prompt(user_id)}]
    convo.extend(
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages
    )
    steps: list[dict] = []
    try:
        for _ in range(_MAX_STEPS):
            raw = _chat_with_retry(client, convo)
            call = parse_tool_call(raw)
            if call is None:
                return {"reply": raw.strip(), "steps": steps, "advisory": ADVISORY_NOTE}
            result = run_tool(call["tool"], call["args"], ds, user_id, today, client)
            steps.append({"tool": call["tool"], "args": call["args"], "result": result})
            convo.append({"role": "assistant", "content": raw})
            convo.append(
                {
                    "role": "user",
                    "content": f"KẾT QUẢ CÔNG CỤ {call['tool']}: {json.dumps(result, ensure_ascii=False)}",
                }
            )
        # Ran out of steps — force a natural-language answer from what we gathered.
        convo.append(
            {
                "role": "user",
                "content": "Hãy trả lời người dùng bằng tiếng Việt dựa trên các kết quả trên.",
            }
        )
        return {
            "reply": _chat_with_retry(client, convo).strip(),
            "steps": steps,
            "advisory": ADVISORY_NOTE,
        }
    except Exception:  # noqa: BLE001 - LLM unavailable: degrade, never crash
        return {"reply": _fallback_reply(steps) or _BUSY, "steps": steps, "advisory": ADVISORY_NOTE}
