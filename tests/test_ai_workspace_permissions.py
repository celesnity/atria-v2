"""Permission test cases (P1 deliverable: >=5).

Curated, policy-verified (user, document, expected) triples over real seeded
documents — covering public/internal-for-all, own-department Confidential,
cross-department Confidential denial, and Restricted (Executive-only). The
dataset's Public_Evaluation set is a retrieval oracle (multi-doc answers,
question-level labels) and is not a clean pure-ACL truth table, so these cases
are derived from the written access policy instead.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

_MODULE = Path(__file__).resolve().parent.parent / "modules" / "ai_workspace"
_SCRIPTS = _MODULE / "scripts"
_TOOLS = _MODULE / "tools"
for _p in (str(_SCRIPTS), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import access  # noqa: E402
import repo  # noqa: E402
import seed_db  # noqa: E402

_CASES = list(csv.DictReader(open(_MODULE / "access" / "permission_tests.csv", encoding="utf-8")))


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("aiwperm")
    import os

    os.environ["AIW_DB_PATH"] = str(tmp / "aiw.db")
    os.environ["AIW_UPLOADS_DIR"] = str(tmp / "uploads")
    os.environ["AIW_AUDIT_LOG"] = str(tmp / "audit.jsonl")
    seed_db.seed()
    yield
    for k in ("AIW_DB_PATH", "AIW_UPLOADS_DIR", "AIW_AUDIT_LOG"):
        os.environ.pop(k, None)


def test_dataset_has_allow_and_deny_cases():
    labels = {c["expected"] for c in _CASES}
    assert "Allow" in labels and "Deny" in labels
    assert sum(1 for c in _CASES if c["expected"] == "Deny") >= 5


@pytest.mark.parametrize("case", _CASES, ids=[c["test_id"] for c in _CASES])
def test_permission_case(seeded, case):
    matrix = repo.load_access_matrix()
    user = repo.load_user(case["user_id"])
    doc = repo.get_document(case["doc_id"])
    assert user is not None and doc is not None
    decision = access.decide(
        user.role, user.department, doc["classification"], doc["department"], matrix
    )
    assert decision.allowed is (case["expected"] == "Allow"), (
        f"{case['test_id']}: {case['user_id']} x {case['doc_id']} "
        f"expected {case['expected']}, got {decision.reason}"
    )
