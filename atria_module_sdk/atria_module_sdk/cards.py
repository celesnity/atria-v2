"""Card helpers — the structured UI payloads a connector broadcasts.

A *card* is a JSON object the Atria web UI renders. Atria labels it with a
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
    """Federated chat-block descriptor matching Atria's ``custom_block`` render:'remote'."""
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
