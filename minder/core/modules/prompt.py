"""Build the module catalog injected into every conversation's system prompt.

Per module it emits the one-line description, the "When to use" triggers, and
an index of sub-skills. Modules are used by running their scripts (via bash) or
calling any remote proxy tools they expose.
"""

from __future__ import annotations

import re
from pathlib import Path

from minder.core.modules.registry import ModuleRegistry
from minder.core.modules.store import Module, parse_frontmatter

_HEADING_RE = re.compile(r"^#{1,6}\s")


def _format_root(root: Path) -> str:
    """Render the modules root as ``~/...`` when under $HOME, else absolute."""
    try:
        home = Path.home()
        if root.is_relative_to(home):
            return "~/" + str(root.relative_to(home))
    except (AttributeError, ValueError):
        pass
    return str(root)


def _header(root: Path) -> str:
    r = _format_root(root)
    return (
        "## Active Modules\n\n"
        f"Modules root: ``{r}``\n\n"
        f"The following modules are installed under ``{r}/<name>/``. Each module is "
        "a self-contained skill folder. Only a short summary is shown here; the "
        "full instructions load **on demand** so the prompt stays small.\n\n"
        "**Module instructions are shown inline below** — each module's description, "
        "triggers, and sub-skill index are listed.\n\n"
        "**Running scripts:** ``python <absolute-path>/<name>/scripts/<file>.py`` "
        "(via bash). **Always use absolute paths** — your bash CWD is the chat "
        f"workspace, NOT the modules root. Example: ``python {r}/<name>/scripts/<file>.py``.\n"
    )


def _extract_section(body: str, heading: str) -> str:
    """Return the text under a ``## <heading>`` (case-insensitive).

    Capture stops at the next markdown heading. Returns ``""`` if not found.
    """
    target = heading.strip().lower()
    out: list[str] = []
    capturing = False
    for line in body.splitlines():
        if _HEADING_RE.match(line):
            if capturing:
                break
            capturing = line.lstrip("#").strip().lower() == target
            continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def _format_files(files: list[str]) -> str:
    """Return a compact one-line listing of a module's files, capped for length."""
    interesting = [f for f in files if f != "SKILL.md" and not f.startswith("skills/")]
    if not interesting:
        return ""
    shown = interesting[:20]
    suffix = (
        "" if len(interesting) == len(shown) else f", … (+{len(interesting) - len(shown)} more)"
    )
    return f"Files: {', '.join(shown)}{suffix}"


def render_module_section(m: Module) -> list[str]:
    """Render one module's catalog lines (heading, summary, sub-skill index)."""
    _, body = parse_frontmatter(m.skill_md)
    section = [f"### {m.name}", "", (m.description or "").strip()]

    when = _extract_section(body, "When to use")
    if when:
        section += ["", "**When to use:**", when]

    if m.subskills:
        section += ["", "**Sub-skills**:"]
        for s in m.subskills:
            section.append(f'- `{m.name}:{s.name}` — {s.description}')

    listing = _format_files(list(m.files))
    if listing:
        section += ["", listing]
    return section


def build_skill_block(registry: ModuleRegistry) -> str:
    """Return the lazy module catalog (header + a summary per module). Empty if none."""
    modules = registry.all()
    if not modules:
        return ""
    parts = [_header(registry.root)]
    for m in modules:
        section_lines = render_module_section(m)
        parts.append("\n".join(section_lines) + "\n")
    return "\n".join(parts)
