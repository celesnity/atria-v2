"""Built-in tool schemas: file tools.

The file/code tools (write_file, edit_file, read_file, list_files, search) were
removed — this agent no longer reads, writes, or searches files. The list is kept
(empty) so the assembly in ``builtin/__init__.py`` stays stable.
"""

from __future__ import annotations

from typing import Any

SCHEMAS: list[dict[str, Any]] = []
