"""Data-extractor subagent registration smoke test."""

from atria.core.agents.subagents.agents import ALL_SUBAGENTS
from atria.core.agents.subagents.agents.data_extractor import DATA_EXTRACTOR_SUBAGENT


def test_subagent_registered() -> None:
    assert DATA_EXTRACTOR_SUBAGENT in ALL_SUBAGENTS
    assert DATA_EXTRACTOR_SUBAGENT["name"] == "Data-Extractor"
    assert "run_sql" in DATA_EXTRACTOR_SUBAGENT["tools"]
    assert "bash" not in DATA_EXTRACTOR_SUBAGENT["tools"]
    assert "write_file" not in DATA_EXTRACTOR_SUBAGENT["tools"]
