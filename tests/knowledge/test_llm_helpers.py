from typing import Any

from minder.core.knowledge.extraction import extract_entities
from minder.core.knowledge.summarize import summarize_document


def test_summary_trims_and_returns_text() -> None:
    assert summarize_document("body", lambda msgs: "  a summary  ") == "a summary"


def test_summary_failure_returns_empty() -> None:
    def boom(msgs: list[dict[str, Any]]) -> str:
        raise RuntimeError("llm down")

    assert summarize_document("body", boom) == ""


def test_extract_parses_entities_and_filters_types() -> None:
    payload = (
        '{"entities":[{"key":"leave-policy","type":"Policy"},'
        '{"key":"junk","type":"Bogus"}],'
        '"relations":[{"src":"leave-policy","dst":"hr","confidence":0.8}]}'
    )
    entities, relations = extract_entities("t", lambda msgs: payload)
    assert ("leave-policy", "Policy") in entities
    assert ("junk", "Bogus") not in entities
    assert relations == [("leave-policy", "hr", 0.8)]


def test_extract_malformed_json_is_empty() -> None:
    assert extract_entities("t", lambda msgs: "not json") == ([], [])
