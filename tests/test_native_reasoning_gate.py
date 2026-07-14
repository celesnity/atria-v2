"""Unit tests for the thinking-phase gate helper."""

from minder.core.agents.execution.react_executor.iteration import _should_run_thinking


def test_native_reasoning_skips_thinking():
    # When native reasoning is on, the prompted thinking phase never runs,
    # even if thinking is visible and not otherwise skipped.
    assert _should_run_thinking(
        native_reasoning=True, thinking_visible=True, should_skip_thinking=False
    ) is False


def test_prompted_thinking_runs_when_native_off():
    assert _should_run_thinking(
        native_reasoning=False, thinking_visible=True, should_skip_thinking=False
    ) is True


def test_prompted_thinking_respects_visibility_and_skip():
    assert _should_run_thinking(
        native_reasoning=False, thinking_visible=False, should_skip_thinking=False
    ) is False
    assert _should_run_thinking(
        native_reasoning=False, thinking_visible=True, should_skip_thinking=True
    ) is False
