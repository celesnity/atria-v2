"""Permission-aware hybrid search provider over the enterprise document corpus."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acl import allowed_clause, qdrant_acl_filter  # noqa: E402

from atria.core.context_engineering.search import pg  # noqa: E402
from atria.core.context_engineering.search.dense import DenseIndex  # noqa: E402
from atria.core.context_engineering.search.embedder import Embedder  # noqa: E402
from atria.core.context_engineering.search.fusion import (  # noqa: E402
    facet_counts,
    rrf_fuse,
    top_margin,
)
from atria.core.context_engineering.search.normalize import normalize_for_search  # noqa: E402
from atria.core.context_engineering.search.provider import SearchProvider  # noqa: E402
from atria.core.context_engineering.search.types import (  # noqa: E402
    SearchContext,
    SearchHit,
    SourceResults,
)

_RECALL = 30
_SNIPPET_CHARS = 350
_COLLECTION = "enterprise_chunks"


def _resolve_identity(user_id: str | None) -> tuple[str, str | None]:
    """Map a dataset user_id to (role, department), degrading safely if unknown.

    Args:
        user_id: The acting user's id in the enterprise dataset (e.g. 'U001'),
            or None when identity could not be established by the runtime.

    Returns:
        A (role, department) tuple. Unknown or unrecognized user_id resolves
        to ("Employee", None) — the most restrictive non-executive view,
        since a blank/None department denies access to Confidential
        documents in both `allowed_clause` and `qdrant_acl_filter`.
    """
    if user_id:
        rows = pg.fetch_all(
            "SELECT role, department FROM enterprise_users WHERE user_id = $1", [user_id]
        )
        if rows:
            return str(rows[0]["role"]), rows[0]["department"]
    return "Employee", None


class DocumentsProvider(SearchProvider):
    """Hybrid (FTS + dense) retrieval with retrieval-time ACL enforcement."""

    name = "documents"
    description = (
        "Vietnamese enterprise knowledge base: company policies, HR, finance, "
        "product, engineering, operations, legal and executive documents. "
        "Results are permission-filtered for the acting user."
    )
    filter_schema: dict[str, Any] = {
        "department": {
            "type": "string",
            "description": (
                "Owning department, English name (e.g. 'Finance', 'Human Resources', "
                "'Engineering'). See result facets for valid values."
            ),
        }
    }

    def __init__(self) -> None:
        """Initialize the embedder and dense index used for recall."""
        self._embedder = Embedder()
        self._dense = DenseIndex(_COLLECTION)

    def search(
        self, query: str, filters: dict[str, Any], limit: int, context: SearchContext
    ) -> SourceResults:
        """Run permission-aware hybrid search over the enterprise document corpus.

        Recalls candidates independently over lexical (Postgres full-text
        search) and dense (Qdrant vector similarity) channels, enforcing the
        same ACL predicate on both, fuses them with reciprocal-rank fusion,
        and collapses results to the single best-scoring chunk per document
        so the agent sees one hit per accessible document.

        Args:
            query: Free-text search query (Vietnamese or diacritics-stripped
                Vietnamese; normalized identically to the indexed content).
            filters: Model-controllable relevance filters. Only `department`
                is honored; classification is policy and is never
                model-controlled.
            limit: Maximum number of document-level hits to return.
            context: Runtime-injected search context carrying `user_id`, used
                to resolve the acting user's role and department for ACL
                enforcement. A missing/unknown user_id degrades to the most
                restrictive non-executive view.

        Returns:
            SourceResults with one hit per accessible document (best chunk
            each), department/classification facets over the returned hits,
            a top_margin ambiguity signal, and a `note` when no accessible
            document matched the query.
        """
        role, user_department = _resolve_identity(context.user_id)
        department_filter = filters.get("department")

        # --- lexical recall (ACL enforced in SQL) ---
        params: list[Any] = [normalize_for_search(query)]
        where = ["tsv @@ websearch_to_tsquery('simple', $1)"]
        if role != "Executive":
            params.append(user_department or "")
            where.append(allowed_clause(role, len(params)))
        if department_filter:
            params.append(department_filter)
            where.append(f"department = ${len(params)}")
        lexical_rows = pg.fetch_all(
            "SELECT chunk_id, document_id, title, department, classification, content, "
            "ts_rank_cd(tsv, websearch_to_tsquery('simple', $1)) AS rank "
            f"FROM enterprise_chunks WHERE {' AND '.join(where)} "
            f"ORDER BY rank DESC LIMIT {_RECALL}",
            params,
        )

        # --- dense recall (same ACL as payload filter) ---
        from qdrant_client import models

        acl = qdrant_acl_filter(role, user_department)
        conditions: list[models.Condition] = list(acl.should) if acl else []
        dense_filter: models.Filter | None = acl
        if department_filter:
            must: list[models.Condition] = [
                models.FieldCondition(
                    key="department", match=models.MatchValue(value=department_filter)
                )
            ]
            dense_filter = models.Filter(must=must, should=conditions or None)
        vector = self._embedder.embed([query])[0]
        dense_hits = self._dense.query(vector, query_filter=dense_filter, limit=_RECALL)

        # --- fuse, hydrate, collapse to best chunk per document ---
        fused = rrf_fuse([[r["chunk_id"] for r in lexical_rows], [h[0] for h in dense_hits]])
        by_id = {r["chunk_id"]: r for r in lexical_rows}
        missing = [cid for cid in fused if cid not in by_id]
        if missing:
            rows = pg.fetch_all(
                "SELECT chunk_id, document_id, title, department, classification, content "
                "FROM enterprise_chunks WHERE chunk_id = ANY($1::text[])",
                [missing],
            )
            by_id.update({r["chunk_id"]: r for r in rows})

        best_per_doc: dict[str, tuple[float, dict[str, Any]]] = {}
        for chunk_id, score in fused.items():
            row = by_id.get(chunk_id)
            if row is None:
                continue
            doc_id = row["document_id"]
            if doc_id not in best_per_doc or score > best_per_doc[doc_id][0]:
                best_per_doc[doc_id] = (score, row)

        ranked = sorted(best_per_doc.values(), key=lambda pair: pair[0], reverse=True)[:limit]
        hits = [
            SearchHit(
                id=row["document_id"],
                source=self.name,
                title=str(row["title"]),
                snippet=str(row["content"])[:_SNIPPET_CHARS],
                score=score,
                metadata={
                    "document_id": row["document_id"],
                    "department": row["department"],
                    "classification": row["classification"],
                },
            )
            for score, row in ranked
        ]
        facet_rows = [
            {"department": row["department"], "classification": row["classification"]}
            for _, row in ranked
        ]
        return SourceResults(
            source=self.name,
            hits=hits,
            facets=facet_counts(facet_rows, ["department", "classification"]),
            top_margin=top_margin([h.score for h in hits]),
            note=None if hits else "No accessible documents matched the query.",
        )


def get_provider() -> DocumentsProvider:
    """Module discovery entry point.

    Returns:
        A new DocumentsProvider instance, used by
        `discover_module_providers` to register this module's search
        provider.
    """
    return DocumentsProvider()
