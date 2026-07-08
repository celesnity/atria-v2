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
