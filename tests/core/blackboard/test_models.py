from atria.core.blackboard.models import (
    MAX_NOTE_CHARS,
    VALID_TYPES,
    Note,
)


def test_valid_types_and_cap():
    # S1: per-type caps collapsed to a single budget (DeLM Fig 4b: length-insensitive).
    assert VALID_TYPES == ("FACT", "TRIED", "OBSERVED", "FAIL", "CLAIM", "PATCH_SUMMARY")
    assert MAX_NOTE_CHARS == 300


def test_note_roundtrips_dict():
    n = Note(type="FACT", content="x.py:1 does y", thread_id=0, ts=123.0)
    d = n.to_dict()
    assert d == {"type": "FACT", "content": "x.py:1 does y", "thread_id": 0, "ts": 123.0}
    assert Note.from_dict(d) == n


def test_task_roundtrips_through_dict():
    from atria.core.blackboard.models import Task, TASK_STATUSES

    assert "pending" in TASK_STATUSES and "done" in TASK_STATUSES
    t = Task(id="t0", subagent_type="code_explorer", prompt="find X", ts=1.5)
    assert t.status == "pending" and t.result == ""
    again = Task.from_dict(t.to_dict())
    assert again == t
    done = Task.from_dict({"id": "t1", "subagent_type": "solver", "prompt": "p",
                           "status": "done", "result": "ok", "ts": 2.0})
    assert done.status == "done" and done.result == "ok"
