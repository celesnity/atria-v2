from minder.core.knowledge import assistant_profile


def test_profile_block_prepended_when_present(monkeypatch):
    monkeypatch.setattr(
        assistant_profile, "load_profile_block_sync", lambda tenant: "## Vai trò của bạn\nRocket Helper"
    )
    out = assistant_profile.apply_profile("BASE PROMPT", tenant_id="t1")
    assert out.startswith("## Vai trò của bạn")
    assert "BASE PROMPT" in out


def test_no_profile_returns_base(monkeypatch):
    monkeypatch.setattr(assistant_profile, "load_profile_block_sync", lambda tenant: "")
    assert assistant_profile.apply_profile("BASE PROMPT", tenant_id="t1") == "BASE PROMPT"
