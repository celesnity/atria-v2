"""Unit tests for rendering module declarative context into the SKILL block."""


def test_render_context_block_lists_knowledge_notes_and_hint():
    from minder.core.modules.prompt import _render_context_block

    lines = _render_context_block(
        "module_template",
        {"knowledge": ["Always confirm SKU."], "notes": [{"name": "products", "text": "Catalog."}]},
    )
    text = "\n".join(lines)
    assert "**Domain knowledge:**" in text
    assert "- Always confirm SKU." in text
    assert "- products: Catalog." in text
    assert "read_module_context('module_template')" in text


def test_render_context_block_empty_when_no_context():
    from minder.core.modules.prompt import _render_context_block

    assert _render_context_block("m", {}) == []
    assert _render_context_block("m", {"knowledge": [], "notes": []}) == []
