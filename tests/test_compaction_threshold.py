"""Configurable blocking-compaction threshold (default 90%)."""

from minder.models.config import AppConfig
from minder.core.context_engineering.compaction import ContextCompactor, OptimizationLevel


class _FakeHttp:  # ContextCompactor only stores it; not called by check_usage
    pass


def _compactor_at(pct: float, threshold: float) -> ContextCompactor:
    cfg = AppConfig(max_context_tokens=100_000, compaction_threshold=threshold)
    c = ContextCompactor(cfg, _FakeHttp())
    # Force usage_pct to `pct`: neutralize the recount that check_usage() runs,
    # then pin the token count against max_context.
    c._update_token_count = lambda *a, **k: None  # type: ignore[method-assign]
    c._last_token_count = int(c._max_context * pct)
    return c


def test_default_compaction_threshold_is_90_percent():
    assert AppConfig().compaction_threshold == 0.90


def test_compact_triggers_at_configured_threshold():
    c = _compactor_at(0.91, threshold=0.90)
    assert c.check_usage([], "sys") == OptimizationLevel.COMPACT


def test_no_compact_below_configured_threshold():
    c = _compactor_at(0.88, threshold=0.90)
    assert c.check_usage([], "sys") != OptimizationLevel.COMPACT
