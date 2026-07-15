from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from typing_extensions import Annotated

from minder_python_sdk._schema import MANAGED_PARAMS, build_params_model


def test_basic_scalars_required_and_optional():
    def handler(query: str, limit: int = 10):
        ...

    model = build_params_model(handler)
    schema = model.model_json_schema()
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["limit"]["type"] == "integer"
    assert schema["required"] == ["query"]  # limit has a default


def test_optional_and_list_and_enum():
    class Color(str, Enum):
        red = "red"
        blue = "blue"

    def handler(tags: list[str], note: Optional[str] = None, color: Color = Color.red):
        ...

    schema = build_params_model(handler).model_json_schema()
    assert schema["properties"]["tags"]["type"] == "array"
    assert "note" not in schema.get("required", [])
    assert "color" in schema["properties"]


def test_nested_pydantic_model():
    class Address(BaseModel):
        city: str
        zip: str

    def handler(addr: Address):
        ...

    schema = build_params_model(handler).model_json_schema()
    assert "addr" in schema["properties"]


def test_field_description_passthrough():
    def handler(sku: Annotated[str, Field(description="stock unit")]):
        ...

    schema = build_params_model(handler).model_json_schema()
    assert schema["properties"]["sku"]["description"] == "stock unit"


def test_managed_params_excluded():
    def handler(query: str, principal=None, session_id=None, autonomy=None,
                dry_run=False, **kwargs):
        ...

    schema = build_params_model(handler).model_json_schema()
    props = schema["properties"]
    assert set(props) == {"query"}
    for name in MANAGED_PARAMS:
        assert name not in props


def test_unannotated_param_is_any_not_required_by_type():
    def handler(payload):  # no annotation, no default
        ...

    model = build_params_model(handler)
    assert "payload" in model.model_json_schema()["properties"]


def test_no_data_params_returns_none():
    def handler(principal=None, **kwargs):
        ...

    assert build_params_model(handler) is None


def test_secret_params_excluded_from_schema():
    from minder_python_sdk._schema import build_params_model, secret_params
    from minder_python_sdk._secret import Secret

    def handler(query: str, token: Secret):
        ...

    schema = build_params_model(handler).model_json_schema()
    assert "token" not in schema["properties"]
    assert "query" in schema["properties"]
    assert "token" in secret_params(handler)
