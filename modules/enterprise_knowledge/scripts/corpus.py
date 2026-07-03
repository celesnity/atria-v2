"""Parse enterprise documents into structured Document records.

A source file starts with a ``---``-delimited front-matter block declaring
``doc_id``, ``title``, ``department`` (canonical department_id), and
``classification``, optionally ``owner``, ``knowledge_space``, ``last_updated``,
``language`` — followed by the Vietnamese body. Only ``.md``/``.txt`` are handled.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REQUIRED = ("doc_id", "title", "department", "classification")

# Canonical department_id -> knowledge space (used to derive when absent).
_KNOWLEDGE_SPACE = {
    "COMP": "Company Knowledge",
    "EXEC": "Executive Knowledge",
}
_DEPARTMENT_KNOWLEDGE = "Department Knowledge"


@dataclass(frozen=True)
class Document:
    """A parsed enterprise document: front-matter metadata plus body text."""

    doc_id: str
    title: str
    department: str
    classification: str
    owner: str
    knowledge_space: str
    last_updated: str
    language: str
    path: str
    text: str


def knowledge_space_for(department: str) -> str:
    """Derive the knowledge space from a canonical department_id."""
    return _KNOWLEDGE_SPACE.get(department, _DEPARTMENT_KNOWLEDGE)


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body). Front-matter is a leading ``---`` ... ``---`` block."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    meta: dict[str, str] = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        key, sep, value = lines[i].partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip('"').strip("'")
    body = "\n".join(lines[body_start:]).lstrip("\n")
    return meta, body


def parse_document(path: str) -> Document:
    """Parse a single ``.md``/``.txt`` file into a :class:`Document`.

    Raises:
        ValueError: If a required front-matter key is missing.
    """
    raw = Path(path).read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw)
    for key in _REQUIRED:
        if key not in meta:
            raise ValueError(f"{path}: missing front-matter key {key!r}")
    department = str(meta["department"])
    return Document(
        doc_id=meta["doc_id"],
        title=meta["title"],
        department=department,
        classification=meta["classification"],
        owner=meta.get("owner", department),
        knowledge_space=meta.get("knowledge_space") or knowledge_space_for(department),
        last_updated=meta.get("last_updated", ""),
        language=meta.get("language", "vi"),
        path=path,
        text=body,
    )


def load_corpus(root: str) -> list[Document]:
    """Parse every ``.md``/``.txt`` directly under ``root``, sorted by filename."""
    paths = sorted(
        p for p in Path(root).iterdir()
        if p.suffix in (".md", ".txt") and p.is_file()
    )
    return [parse_document(str(p)) for p in paths]
