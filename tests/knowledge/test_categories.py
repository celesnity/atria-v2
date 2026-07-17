import pytest
from minder.core.knowledge.categories import (
    Category,
    behavior_for,
    is_valid_category,
)


def test_reference_docs_retrieves_and_graphs():
    b = behavior_for("reference_docs")
    assert b.inject is False
    assert b.build_graph is True
    assert b.summarize is False


def test_persona_injects_and_summarizes_no_graph():
    b = behavior_for("persona")
    assert b.inject is True
    assert b.summarize is True
    assert b.build_graph is False


def test_company_background_matches_persona_behavior():
    assert behavior_for("company_background").inject is True
    assert behavior_for("company_background").build_graph is False


def test_unknown_category_rejected():
    assert is_valid_category("reference_docs") is True
    assert is_valid_category("nope") is False
    with pytest.raises(ValueError):
        behavior_for("nope")


def test_category_enum_values_are_stable_strings():
    assert Category.PERSONA.value == "persona"
    assert Category.REFERENCE_DOCS.value == "reference_docs"
