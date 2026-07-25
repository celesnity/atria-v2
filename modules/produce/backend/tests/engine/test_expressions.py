from engine.core.expressions import resolve

NODES = {"measure": {"value": 7.0}, "op": {"name": "Ann"}}


def test_single_expression_returns_typed_value():
    assert resolve("{{ nodes.measure.output.value }}", NODES, {}) == 7.0


def test_inputs_expression():
    assert resolve("{{ inputs.line }}", NODES, {"line": "A"}) == "A"


def test_mixed_text_interpolates_to_string():
    assert resolve("hi {{ nodes.op.output.name }}", NODES, {}) == "hi Ann"


def test_non_string_passthrough():
    assert resolve(10, NODES, {}) == 10


def test_unknown_expression_left_verbatim_in_mixed_text():
    assert resolve("x {{ nodes.nope.output.v }}", NODES, {}) == "x {{ nodes.nope.output.v }}"
