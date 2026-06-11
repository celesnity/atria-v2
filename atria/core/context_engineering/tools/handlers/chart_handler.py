"""Dispatch for the `chart` tool."""

from __future__ import annotations

from typing import Any, Dict


class ChartHandler:
    def __init__(self, tool: Any) -> None:
        self._tool = tool

    def chart(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self._tool:
            return {"success": False, "output": None, "error": "ChartTool not available"}
        return self._tool.render(
            db_path=args["db_path"],
            source_table=args["source_table"],
            chart_type=args["chart_type"],
            x=args["x"],
            y=args["y"],
            title=args["title"],
            out_path=args["out_path"],
            agg=args.get("agg"),
        )
