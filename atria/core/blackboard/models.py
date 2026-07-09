"""Typed-note model and size caps for the shared blackboard."""
from __future__ import annotations

from dataclasses import dataclass

VALID_TYPES: tuple[str, ...] = ("FACT", "TRIED", "OBSERVED", "FAIL", "CLAIM", "PATCH_SUMMARY")
# Single note budget. The DeLM paper (Fig 4b) shows accuracy is insensitive to gist
# length past ~100 tokens, so per-type char caps are tuning noise; one budget that
# fits the largest type (PATCH_SUMMARY's "files=A | idea=B | evidence=C | risk=D"
# schema) suffices for all types.
MAX_NOTE_CHARS = 300


@dataclass(frozen=True)
class Note:
    """One typed entry on the blackboard."""

    type: str
    content: str
    thread_id: int
    ts: float

    def to_dict(self) -> dict:
        return {"type": self.type, "content": self.content,
                "thread_id": self.thread_id, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Note":
        return cls(type=d["type"], content=d["content"],
                   thread_id=int(d["thread_id"]), ts=float(d["ts"]))


TASK_STATUSES: tuple[str, ...] = ("pending", "claimed", "done", "failed")


@dataclass(frozen=True)
class Task:
    """One unit of delegated work on the blackboard task channel."""

    id: str
    subagent_type: str
    prompt: str
    status: str = "pending"
    result: str = ""
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "subagent_type": self.subagent_type,
                "prompt": self.prompt, "status": self.status,
                "result": self.result, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(id=d["id"], subagent_type=d["subagent_type"], prompt=d["prompt"],
                   status=d.get("status", "pending"), result=d.get("result", ""),
                   ts=float(d.get("ts", 0.0)))


REQUEST_STATUSES: tuple[str, ...] = ("open", "answered", "closed")


@dataclass(frozen=True)
class Request:
    """One un-addressed request the main agent posts to board β (paper §3)."""

    id: str
    prompt: str
    status: str = "open"
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "prompt": self.prompt,
                "status": self.status, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Request":
        return cls(id=d["id"], prompt=d["prompt"],
                   status=d.get("status", "open"), ts=float(d.get("ts", 0.0)))


@dataclass(frozen=True)
class Response:
    """One helper's answer on the response board β_r (exclusive to the main agent)."""

    request_id: str
    responder: str
    content: str
    confidence: float = 0.0
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"request_id": self.request_id, "responder": self.responder,
                "content": self.content, "confidence": self.confidence, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Response":
        return cls(request_id=d["request_id"], responder=d["responder"],
                   content=d["content"], confidence=float(d.get("confidence", 0.0)),
                   ts=float(d.get("ts", 0.0)))


@dataclass(frozen=True)
class Bid:
    """One helper's autonomous self-assessment of a request (for telemetry/viewer)."""

    request_id: str
    responder: str
    volunteered: bool
    reason: str = ""
    confidence: float = 0.0
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"request_id": self.request_id, "responder": self.responder,
                "volunteered": self.volunteered, "reason": self.reason,
                "confidence": self.confidence, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Bid":
        return cls(request_id=d["request_id"], responder=d["responder"],
                   volunteered=bool(d["volunteered"]), reason=d.get("reason", ""),
                   confidence=float(d.get("confidence", 0.0)), ts=float(d.get("ts", 0.0)))
