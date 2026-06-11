"""Dispatch for the `md_to_pdf` tool."""

from __future__ import annotations

from typing import Any, Dict


class MdToPdfHandler:
    def __init__(self, tool: Any) -> None:
        self._tool = tool

    def md_to_pdf(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self._tool:
            return {"success": False, "output": None, "error": "MdToPdfTool not available"}
        return self._tool.render(args["md_path"], args["pdf_path"])
