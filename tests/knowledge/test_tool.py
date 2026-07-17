from minder.core.context_engineering.search.types import SearchContext, SearchHit, SourceResults
from minder.core.knowledge.tool import build_knowledge_tool_spec


class FakeProvider:
    def search(self, question, filters, limit, context):
        assert "tenant_id" not in filters  # tenant never model-supplied
        return SourceResults(
            source="documents",
            hits=[SearchHit("1#0", "documents", "A", "alpha", 0.9, {"citation": "A [1] · 1#0"})],
        )


def test_tool_spec_shape_and_no_tenant_param():
    spec = build_knowledge_tool_spec(FakeProvider(), lambda: SearchContext("U1"))
    assert spec.name == "knowledge_query"
    props = spec.parameters["properties"]
    assert "question" in props and "tenant_id" not in props
    assert spec.parameters["required"] == ["question"]


def test_handler_returns_hits():
    spec = build_knowledge_tool_spec(FakeProvider(), lambda: SearchContext("U1"))
    out = spec.handler(question="alpha", category="reference_docs", k=3)
    assert out["hits"][0]["metadata"]["citation"] == "A [1] · 1#0"
