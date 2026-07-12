"""Garage-copilot ("vibe repairing") system-prompt section.

Sessions whose metadata declares ``session_type: garage`` get the copilot
persona (``main-garage-copilot.md``) plus a dynamic Repair Order anchor block
carrying the session's actual RO/VIN/brand. Injected by the web agent executor
alongside the persona/workspace blocks — the PromptComposer never sees session
context, so this section is deliberately NOT registered in ``create_composer``
(recorded design deviation, see the garage-copilot implementation doc).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

GARAGE_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "system" / "main" / "main-garage-copilot.md"
)


def _load_template() -> str:
    content = GARAGE_TEMPLATE_PATH.read_text(encoding="utf-8")
    # Strip the leading HTML comment frontmatter, same as PromptComposer does.
    return re.sub(r"^\s*<!--.*?-->\s*", "", content, flags=re.DOTALL).strip()


def build_garage_section(metadata: Optional[dict[str, Any]]) -> str:
    """Return the garage-copilot prompt addition for a session, or ``""``.

    Args:
        metadata: The session's metadata dict (``Session.metadata``).

    Returns:
        Section template plus the RO anchor block for garage sessions;
        empty string for every other session so the persona never leaks.
    """
    if not metadata or metadata.get("session_type") != "garage":
        return ""

    technician = str(metadata.get("technician") or "").strip() or "(chưa ghi tên)"
    anchor = (
        "### Phiên làm việc này (RO anchor)\n\n"
        f"- Repair Order: {metadata.get('ro_number', '')}\n"
        f"- VIN: {metadata.get('vin', '')}\n"
        f"- Hãng xe: {metadata.get('brand', '')}\n"
        f"- Kỹ thuật viên: {technician}"
    )
    return f"{_load_template()}\n\n{anchor}"
