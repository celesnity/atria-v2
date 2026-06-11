"""Skill entry point: register() returns ToolSpecs for deep_research."""

from __future__ import annotations

from pathlib import Path

from atria.core.skill_tools import SkillToolContext, ToolSpec

from .engine import DeepResearchEngine
from .schemas import PARAMS_DEEP_RESEARCH, PARAMS_GET_RESEARCH_STATUS


def register(ctx: SkillToolContext) -> list[ToolSpec]:
    engine = DeepResearchEngine(ctx)
    here = Path(__file__).parent
    return [
        ToolSpec(
            name="deep_research",
            description="Generate a research taxonomy and run a background research pipeline.",
            parameters=PARAMS_DEEP_RESEARCH,
            handler=engine.deep_research,
            card_path=here / "cards" / "deep_research.md",
        ),
        ToolSpec(
            name="get_research_status",
            description="Check the status of a background research job.",
            parameters=PARAMS_GET_RESEARCH_STATUS,
            handler=engine.get_research_status,
            card_path=here / "cards" / "get_research_status.md",
        ),
    ]
