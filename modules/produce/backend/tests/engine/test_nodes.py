from engine.nodes import NODE_TYPES, primitives_metadata


def test_four_primitives():
    assert set(NODE_TYPES) == {"begin", "end", "human", "decision"}


def test_metadata_shape_for_palette():
    md = {m["node_type"]: m for m in primitives_metadata()}
    assert md["human"]["category"]
    assert isinstance(md["decision"]["inputs"], list)
    # human exposes an output_contract + instructions + assignment_rule field
    names = {f["name"] for f in md["human"]["inputs"]}
    assert {"output_contract", "instructions", "assignment_rule"} <= names
