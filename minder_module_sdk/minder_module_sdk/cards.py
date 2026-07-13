"""Card helpers — the structured UI payloads a connector broadcasts.

A *card* is a JSON object the Minder web UI renders. Minder labels it with a
``card_type`` so the UI can pick a renderer; if you don't set one it defaults to
``{module}_card`` and the UI uses its generic card renderer.

These helpers are intentionally minimal and domain-agnostic. Modules with a
richer schema (citations, confidence bands, …) can return any dict they like —
the SDK never forces this shape.
"""

from __future__ import annotations

from typing import Any, Optional


def card(
    answer: str,
    *,
    card_type: Optional[str] = None,
    confidence: Optional[float] = None,
    review_required: bool = False,
    validation_warnings: Optional[list[str]] = None,
    **extra: Any,
) -> dict:
    """Build a generic card dict. ``extra`` merges arbitrary domain fields."""
    band = None
    if confidence is not None:
        band = "low" if confidence < 0.4 else "medium" if confidence < 0.6 else "high"
    out: dict = {
        "answer": answer,
        "confidence": confidence,
        "confidence_band": band,
        "review_required": review_required,
        "validation_warnings": validation_warnings or [],
    }
    if card_type:
        out["card_type"] = card_type
    out.update(extra)
    return out


def block(
    component: str,
    props: Optional[dict] = None,
    *,
    remote_name: str,
    remote_entry: str,
    height: Any = "auto",
    title: Optional[str] = None,
) -> dict:
    """Federated chat-block descriptor matching Minder's ``custom_block`` render:'remote'."""
    return {
        "render": "remote",
        "remote_name": remote_name,
        "remote_entry": remote_entry,
        "component": component,
        "props": props or {},
        "api_base": remote_entry.split("/dashboard/")[0],
        "height": height,
        "title": title,
    }


def assumption(text: str, confidence: Optional[float] = None) -> dict:
    """One entry in a decision packet's assumption ledger: what the agent is
    taking as given, and how sure it is (0..1)."""
    band = None
    if confidence is not None:
        band = "low" if confidence < 0.4 else "medium" if confidence < 0.6 else "high"
    return {"text": text, "confidence": confidence, "confidence_band": band}


def decision_packet(
    action: str,
    arguments: Optional[dict] = None,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    assumptions: Optional[list[dict]] = None,
    risk: str = "low",
    reversible: Optional[bool] = None,
    undo: Optional[str] = None,
    preview: Any = None,
    card_type: str = "decision_packet",
) -> dict:
    """A proposed action packaged for a human to approve / modify / reject.

    Carries the action name + arguments the agent wants to run, an assumption
    ledger (see :func:`assumption`), the action's risk band, and whether it is
    reversible (and how). The UI SDK's ``DecisionPacket`` renders this and posts
    the human's decision back.
    """
    return {
        "card_type": card_type,
        "kind": "decision",
        "action": action,
        "arguments": arguments or {},
        "title": title or action.replace("_", " ").title(),
        "summary": summary,
        "assumptions": assumptions or [],
        "risk": risk,
        "reversible": reversible,
        "undo": undo,
        "preview": preview,
        "review_required": True,
    }


def unavailable_card(reason: str, *, service: str = "service") -> dict:
    """A fail-closed card for a downstream sidecar/service being unreachable."""
    return {
        "answer": reason,
        "answer_type": "clarification_needed",
        "confidence": 0.0,
        "confidence_band": "low",
        "review_required": True,
        "validation_warnings": [f"service_unavailable:{service}"],
    }


def unavailable_suffix(module: str, service: str = "service") -> str:
    """System directive telling the model not to freelance when a sidecar is down."""
    return (
        f"\n\n[SYSTEM: The {module} module's {service} is unavailable. Tell the user "
        "this tool cannot answer right now and that the card above explains why. Do "
        "NOT answer from your own knowledge or read the module's data files to work "
        "around the outage.]"
    )
