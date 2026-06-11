"""Skill entry point: register() returns ToolSpecs for deep_analyze."""

from __future__ import annotations

from pathlib import Path

from atria.core.skill_tools import SkillToolContext, ToolSpec

from .engine import DeepAnalyzeEngine
from .schemas import (
    PARAMS_CANCEL_ANALYZE,
    PARAMS_DEEP_ANALYZE,
    PARAMS_GET_ANALYZE_STATUS,
)


def register(ctx: SkillToolContext) -> list[ToolSpec]:
    engine = DeepAnalyzeEngine(ctx)
    here = Path(__file__).parent
    return [
        ToolSpec(
            name="deep_analyze",
            description="Analyze a tabular data file end-to-end and produce a PDF report.",
            parameters=PARAMS_DEEP_ANALYZE,
            handler=engine.deep_analyze,
            card_path=here / "cards" / "deep_analyze.md",
        ),
        ToolSpec(
            name="get_analyze_status",
            description="Check status of a deep_analyze job.",
            parameters=PARAMS_GET_ANALYZE_STATUS,
            handler=engine.get_analyze_status,
            card_path=here / "cards" / "get_analyze_status.md",
        ),
        ToolSpec(
            name="cancel_analyze",
            description="Cancel a running deep_analyze job.",
            parameters=PARAMS_CANCEL_ANALYZE,
            handler=engine.cancel_analyze,
            card_path=here / "cards" / "cancel_analyze.md",
        ),
    ]
