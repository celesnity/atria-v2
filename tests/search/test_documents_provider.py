"""Live integration tests for the permission-aware documents provider."""

import importlib.util
import os
from pathlib import Path

import pytest

from atria.core.context_engineering.search import pg
from atria.core.context_engineering.search.types import SearchContext

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and (os.environ.get("SEARCH_EMBED_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    ),
    reason="needs live Postgres, Qdrant and an embedding key (run Task 7 ingest first)",
)

_PROVIDER_PATH = (
    Path(__file__).resolve().parents[2] / "modules" / "enterprise_search" / "search_provider.py"
)


def _provider():
    # unique module name: avoids sys.modules collision with the maps provider test
    spec = importlib.util.spec_from_file_location("enterprise_sp_under_test", _PROVIDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_provider()


def _any_user(role: str) -> dict:
    rows = pg.fetch_all(
        "SELECT user_id, role, department FROM enterprise_users WHERE role = $1 LIMIT 1", [role]
    )
    assert rows, f"ingest first: no user with role {role}"
    return rows[0]


def _confidential_doc() -> dict:
    rows = pg.fetch_all(
        "SELECT document_id, title, department FROM enterprise_documents "
        "WHERE classification = 'Confidential' LIMIT 1"
    )
    assert rows, "ingest first: no confidential documents"
    return rows[0]


def test_employee_finds_public_policy_documents():
    employee = _any_user("Employee")
    results = _provider().search(
        "chính sách nghỉ phép của công ty", {}, 5, SearchContext(user_id=employee["user_id"])
    )
    assert results.hits, "expected at least one accessible hit"
    assert all(h.metadata["classification"] != "Restricted" for h in results.hits)
    assert results.facets.get("classification")


def test_restricted_documents_never_surface_for_employee():
    employee = _any_user("Employee")
    results = _provider().search(
        "chiến lược tài chính bí mật", {}, 10, SearchContext(user_id=employee["user_id"])
    )
    assert all(h.metadata["classification"] != "Restricted" for h in results.hits)


def test_confidential_visible_only_to_owning_department_and_executive():
    doc = _confidential_doc()
    provider = _provider()
    # a user OUTSIDE the owning department must not see it
    outsider = pg.fetch_all(
        "SELECT user_id FROM enterprise_users WHERE department <> $1 "
        "AND role <> 'Executive' LIMIT 1",
        [doc["department"]],
    )[0]
    out_results = provider.search(doc["title"], {}, 10, SearchContext(user_id=outsider["user_id"]))
    assert all(h.metadata["document_id"] != doc["document_id"] for h in out_results.hits)
    # an executive must be able to see it
    executive = _any_user("Executive")
    exec_results = provider.search(
        doc["title"], {}, 10, SearchContext(user_id=executive["user_id"])
    )
    assert any(h.metadata["document_id"] == doc["document_id"] for h in exec_results.hits)


def test_unknown_identity_degrades_to_public_internal_only():
    results = _provider().search("báo cáo", {}, 10, SearchContext(user_id=None))
    assert all(h.metadata["classification"] in ("Public", "Internal") for h in results.hits)


def test_department_filter_narrows_results():
    executive = _any_user("Executive")
    results = _provider().search(
        "quy trình", {"department": "Engineering"}, 10, SearchContext(user_id=executive["user_id"])
    )
    assert all(h.metadata["department"] == "Engineering" for h in results.hits)


def test_results_collapse_to_one_hit_per_document():
    employee = _any_user("Employee")
    results = _provider().search("chính sách", {}, 10, SearchContext(user_id=employee["user_id"]))
    doc_ids = [h.metadata["document_id"] for h in results.hits]
    assert len(doc_ids) == len(set(doc_ids))


def test_non_executive_department_filter_still_enforces_acl():
    # the merged must+should dense filter is only built on this path
    doc = _confidential_doc()
    outsider = pg.fetch_all(
        "SELECT user_id, department FROM enterprise_users "
        "WHERE department <> $1 AND role <> 'Executive' LIMIT 1",
        [doc["department"]],
    )[0]
    provider = _provider()
    # outsider explicitly targets the confidential doc's own department via the filter:
    # Public/Internal docs of that department may appear; the confidential one must not.
    results = provider.search(
        doc["title"],
        {"department": doc["department"]},
        10,
        SearchContext(user_id=outsider["user_id"]),
    )
    assert all(h.metadata["document_id"] != doc["document_id"] for h in results.hits)
    assert all(h.metadata["classification"] != "Restricted" for h in results.hits)
    assert all(h.metadata["department"] == doc["department"] for h in results.hits)
    # sanity: an insider CAN see it through the same filtered path
    insider_rows = pg.fetch_all(
        "SELECT user_id FROM enterprise_users "
        "WHERE department = $1 AND role <> 'Executive' LIMIT 1",
        [doc["department"]],
    )
    if insider_rows:
        insider_results = provider.search(
            doc["title"],
            {"department": doc["department"]},
            10,
            SearchContext(user_id=insider_rows[0]["user_id"]),
        )
        assert any(h.metadata["document_id"] == doc["document_id"] for h in insider_results.hits)


def test_withheld_note_signals_permission_denial_to_agent():
    """A non-executive querying content locked to another department gets a
    count-only withheld note — enabling refusal — with nothing disclosed."""
    doc = _confidential_doc()
    outsider = pg.fetch_all(
        "SELECT user_id FROM enterprise_users "
        "WHERE department <> $1 AND role <> 'Executive' LIMIT 1",
        [doc["department"]],
    )[0]
    provider = _provider()
    results = provider.search(doc["title"], {}, 10, SearchContext(user_id=outsider["user_id"]))
    assert all(h.metadata["document_id"] != doc["document_id"] for h in results.hits)
    assert results.note and "withheld" in results.note
    # count only: neither the title nor the document id may leak into the note
    assert doc["document_id"] not in results.note
    assert str(doc["title"]) not in results.note


def test_executive_never_gets_withheld_note():
    doc = _confidential_doc()
    executive = _any_user("Executive")
    provider = _provider()
    results = provider.search(doc["title"], {}, 10, SearchContext(user_id=executive["user_id"]))
    assert not (results.note and "withheld" in results.note)
