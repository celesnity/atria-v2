from typing import Literal

from typing_extensions import Annotated

from minder_python_sdk._secret import (
    OAuth2Secret,
    Secret,
    SecretSpec,
    build_secret,
    resolve_secret_value,
)


def test_resolve_from_header_case_insensitive():
    headers = {"X-Db-Password": "s3cret"}
    assert resolve_secret_value("db_password", headers) == "s3cret"


def test_resolve_from_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "envval")
    assert resolve_secret_value("api_key", None) == "envval"


def test_header_wins_over_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "envval")
    assert resolve_secret_value("api_key", {"x-api_key": "hdr"}) == "hdr"


def test_missing_returns_none():
    assert resolve_secret_value("nope", {}) is None


def test_build_plain_secret():
    s = build_secret(Secret, "raw")
    assert isinstance(s, Secret) and s.value == "raw"


def test_build_oauth2_secret_reads_generic_args():
    ann = OAuth2Secret[Literal["google"], list[Literal["scope.a"]]]
    tok = build_secret(ann, "ya29.token")
    assert tok.access_token == "ya29.token"
    assert tok.provider == "google"
    assert "scope.a" in tok.scopes


def test_secret_spec_tag():
    assert SecretSpec(tag="global").tag == "global"


def test_build_annotated_oauth2_secret_not_downgraded():
    # SecretSpec is documented for exactly this Annotated wrapping; build_secret
    # must see through Annotated and still produce an OAuth2Secret (not a Secret).
    ann = Annotated[
        OAuth2Secret[Literal["google"], list[Literal["scope.a"]]], SecretSpec("global")
    ]
    tok = build_secret(ann, "ya29.token")
    assert isinstance(tok, OAuth2Secret)
    assert tok.access_token == "ya29.token"
    assert tok.provider == "google"
    assert "scope.a" in tok.scopes


def test_annotated_secret_detected_and_excluded():
    from minder_python_sdk._schema import build_params_model, secret_params

    def handler(query: str, token: Annotated[Secret, SecretSpec("global")]):
        ...

    schema = build_params_model(handler).model_json_schema()
    assert "token" not in schema["properties"]
    assert "token" in secret_params(handler)
