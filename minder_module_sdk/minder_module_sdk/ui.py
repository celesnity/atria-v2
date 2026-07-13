"""UI-driving surface — let an agent *use* a module's real UI without scraping.

A module declares its navigable pages, forms (typed fields + a per-form
playbook), and clickable controls; the agent then emits typed **UI intents**
(navigate / fill / focus / highlight / request_confirm / submit) which the
``minder-ui-sdk`` applies to the module's actual React components. The human
still fills blanks and confirms — the agent proposes and points, it does not
click "submit" on a risky action by itself.

Pure data + builders; no ``minder`` import, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

INTENT_TYPES = ("navigate", "fill", "focus", "highlight", "request_confirm", "submit")


# --- declared surface --------------------------------------------------------


@dataclass
class Page:
    """A navigable view inside the module dashboard."""

    id: str
    path: str
    label: str
    description: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "path": self.path, "label": self.label,
                "description": self.description}


@dataclass
class Form:
    """A typed form the agent can prefill. ``submit_tool`` is the gated backend
    action run on submit; ``instructions`` is the per-form playbook the agent
    follows (e.g. 'ask the user to confirm before submitting')."""

    id: str
    route: str
    fields: list[dict]
    submit_tool: Optional[str] = None
    risk: str = "low"
    reversible: Optional[bool] = None
    instructions: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "route": self.route,
            "fields": self.fields,
            "submit_tool": self.submit_tool,
            "risk": self.risk,
            "reversible": self.reversible,
            "instructions": self.instructions,
        }


@dataclass
class Control:
    """A named control (button, toggle) the agent may ask to activate."""

    id: str
    label: str
    route: str = ""
    effect: str = ""
    risk: str = "low"

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "route": self.route,
                "effect": self.effect, "risk": self.risk}


@dataclass
class UiSurface:
    pages: dict[str, Page] = field(default_factory=dict)
    forms: dict[str, Form] = field(default_factory=dict)
    controls: dict[str, Control] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "pages": [p.to_dict() for p in self.pages.values()],
            "forms": [f.to_dict() for f in self.forms.values()],
            "controls": [c.to_dict() for c in self.controls.values()],
        }

    def is_empty(self) -> bool:
        return not (self.pages or self.forms or self.controls)

    def validate(self, intent: dict) -> Optional[str]:
        """Return an error string if the intent targets an undeclared surface,
        else None. Soft — callers may warn rather than reject."""
        kind = intent.get("intent")
        if kind == "navigate" and intent.get("route") not in self.pages:
            return f"unknown route {intent.get('route')!r}"
        if kind in ("fill", "submit") and intent.get("form") not in self.forms:
            return f"unknown form {intent.get('form')!r}"
        if kind == "request_confirm" and intent.get("target") not in self.forms:
            return f"unknown confirm target {intent.get('target')!r}"
        if kind == "highlight" and intent.get("control") not in self.controls:
            return f"unknown control {intent.get('control')!r}"
        return None


# --- intent builders ---------------------------------------------------------


def navigate(route: str) -> dict:
    """Go to a declared page."""
    return {"intent": "navigate", "route": route}


def fill(form: str, values: dict, *, partial: bool = True) -> dict:
    """Prefill a form's fields. ``partial`` leaves fields the agent didn't set
    for the user to complete."""
    return {"intent": "fill", "form": form, "values": values, "partial": partial}


def focus(field_name: str, *, form: Optional[str] = None) -> dict:
    """Point the user at the next field to complete."""
    return {"intent": "focus", "field": field_name, "form": form}


def highlight(control: str) -> dict:
    """Draw attention to a control the user may want to click."""
    return {"intent": "highlight", "control": control}


def request_confirm(target: str, *, summary: Optional[str] = None) -> dict:
    """Hand control to the human: review the filled form/action and confirm."""
    return {"intent": "request_confirm", "target": target, "summary": summary}


def submit(form: str) -> dict:
    """Submit a form (runs its gated ``submit_tool``). Prefer request_confirm
    first for anything above trivial risk."""
    return {"intent": "submit", "form": form}


def is_intent(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("intent") in INTENT_TYPES
