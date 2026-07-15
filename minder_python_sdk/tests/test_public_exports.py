def test_new_public_symbols_importable():
    from minder_python_sdk import (  # noqa: F401
        ActionError,
        OAuth2Secret,
        Response,
        Secret,
        SecretSpec,
    )


def test_version_bumped():
    import minder_python_sdk

    assert minder_python_sdk.__version__ == "0.5.0"
