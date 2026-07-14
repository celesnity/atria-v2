"""Guards for TTFT-critical invariants (see specs/2026-07-13-web-ttft-optimization)."""

from minder.models.config import AppConfig


def test_reasoning_defaults_keep_ttft_low():
    """native_reasoning must default True and reasoning_effort 'minimal' so the
    prompted thinking + critique round-trips never fire on a fresh install."""
    cfg = AppConfig()
    assert cfg.native_reasoning is True
    assert cfg.reasoning_effort == "minimal"


def test_stable_prefix_is_byte_identical_across_volatile_env():
    """The cacheable stable prefix must not contain date/git-status/volatile
    content: two builds differing only by env date must yield identical stable."""
    from minder.core.agents.components.prompts.builders import SystemPromptBuilder
    from minder.core.agents.components.prompts.environment import EnvironmentContext

    def make_env(date: str, git_status: str) -> EnvironmentContext:
        return EnvironmentContext(
            working_dir="/tmp/proj",
            platform="macos",
            os_version="Darwin 25.2.0",
            current_date=date,
            model="gpt-5-mini",
            is_git_repo=True,
            git_status=git_status,
        )

    env_a = make_env("2026-07-13", "clean")
    env_b = make_env("2027-01-01", "M file.py")

    stable_a, _ = SystemPromptBuilder(None, "/tmp/proj", env_context=env_a).build_two_part()
    stable_b, _ = SystemPromptBuilder(None, "/tmp/proj", env_context=env_b).build_two_part()

    assert stable_a == stable_b, "stable prefix changed with volatile env — prefix cache busted"
