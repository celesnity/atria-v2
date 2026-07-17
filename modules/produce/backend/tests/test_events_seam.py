"""Event seam: emit reaches subscribers; no subscriber = harmless no-op."""

from __future__ import annotations

import events


def teardown_function():
    events.clear()


def test_emit_reaches_subscriber():
    seen = []
    events.subscribe(lambda kind, payload: seen.append((kind, payload)))
    events.emit("downtime.opened", {"id": 1})
    assert seen == [("downtime.opened", {"id": 1})]


def test_emit_no_subscriber_is_noop():
    events.emit("job.started", {"id": 9})  # must not raise


def test_listener_error_does_not_propagate():
    def boom(kind, payload):
        raise RuntimeError("listener bug")

    events.subscribe(boom)
    events.emit("andon.raised", {"id": 2})  # must not raise
