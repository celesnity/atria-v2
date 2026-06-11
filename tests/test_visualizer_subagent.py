"""Visualizer subagent registration smoke test."""

from atria.core.agents.subagents.agents import ALL_SUBAGENTS
from atria.core.agents.subagents.agents.visualizer import VISUALIZER_SUBAGENT


def test_visualizer_registered() -> None:
    assert VISUALIZER_SUBAGENT in ALL_SUBAGENTS
    assert VISUALIZER_SUBAGENT["name"] == "Visualizer"
    assert "chart" in VISUALIZER_SUBAGENT["tools"]
    assert "send_data" in VISUALIZER_SUBAGENT["tools"]
    assert "bash" not in VISUALIZER_SUBAGENT["tools"]
