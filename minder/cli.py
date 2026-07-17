"""``minder knowledge`` — manage the Minder knowledge base from the command line.

    minder knowledge list [--tenant T]
        List all documents (id, status, category, title).

    minder knowledge rescan
        Run the seed scan, drain the ingestion queue, and print counts.

    minder knowledge query "<question>" [--tenant T] [--category C] [--k N]
        Semantic search; prints matching hits with citations.

    minder knowledge reingest <doc_id>
        Re-ingest a document by its numeric ID.

    minder knowledge delete <doc_id>
        Delete a document by its numeric ID.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    """List all documents for a tenant."""
    from minder.core.knowledge.cli_ops import format_documents
    from minder.core.knowledge.wiring import build_knowledge_service

    tenant = args.tenant or os.environ.get("KNOWLEDGE_DEV_TENANT", "dev")
    try:
        svc = build_knowledge_service()
        docs = asyncio.run(svc.list_documents(tenant))
        print(format_documents(docs))
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_rescan(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Run seed scan then drain the ingestion queue."""
    from minder.core.knowledge.wiring import build_knowledge_service, run_seed_scan

    try:
        enqueued = run_seed_scan()
        svc = build_knowledge_service()
        processed = asyncio.run(svc.drain_queue())
        print(f"enqueued={enqueued}  processed={processed}")
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Semantic search over the knowledge base."""
    from minder.core.context_engineering.search.types import SearchContext
    from minder.core.knowledge.cli_ops import format_hits
    from minder.core.knowledge.embedding import KnowledgeEmbedder
    from minder.core.knowledge.graph import KnowledgeGraph
    from minder.core.knowledge.provider import DocumentsProvider
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.db.connection import get_sessionmaker

    tenant = args.tenant or os.environ.get("KNOWLEDGE_DEV_TENANT", "dev")
    category = args.category or "reference_docs"
    k = args.k

    try:
        sm = asyncio.run(get_sessionmaker())
        repo = KnowledgeRepository(sm)
        provider = DocumentsProvider(
            KnowledgeEmbedder(),
            repo,
            KnowledgeGraph(),
            lambda _ctx: tenant,
        )
        results = provider.search(
            args.question,
            {"category": category},
            k,
            SearchContext(None),
        )
        print(format_hits([h.to_dict() for h in results.hits]))
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_reingest(args: argparse.Namespace) -> int:
    """Re-ingest a document by its numeric ID."""
    from minder.core.knowledge.wiring import build_knowledge_service

    try:
        svc = build_knowledge_service()
        asyncio.run(svc.reingest(args.doc_id))
        print(f"reingest queued for document {args.doc_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a document by its numeric ID."""
    from minder.core.knowledge.wiring import build_knowledge_service

    try:
        svc = build_knowledge_service()
        asyncio.run(svc.delete(args.doc_id))
        print(f"deleted document {args.doc_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="minder",
        description="Minder CLI — knowledge base management.",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    # knowledge subcommand group
    k_parser = sub.add_parser("knowledge", help="Manage the Minder knowledge base.")
    k_sub = k_parser.add_subparsers(dest="knowledge_cmd", required=True)

    # list
    p_list = k_sub.add_parser("list", help="List all documents.")
    p_list.add_argument("--tenant", default=None, help="Tenant ID (default: $KNOWLEDGE_DEV_TENANT or 'dev')")
    p_list.set_defaults(func=cmd_list)

    # rescan
    p_rescan = k_sub.add_parser("rescan", help="Seed-scan + drain the ingestion queue.")
    p_rescan.set_defaults(func=cmd_rescan)

    # query
    p_query = k_sub.add_parser("query", help="Semantic search over the knowledge base.")
    p_query.add_argument("question", help="Search question.")
    p_query.add_argument("--tenant", default=None, help="Tenant ID.")
    p_query.add_argument("--category", default=None, help="Knowledge category filter.")
    p_query.add_argument("--k", type=int, default=5, help="Number of results (default: 5).")
    p_query.set_defaults(func=cmd_query)

    # reingest
    p_reingest = k_sub.add_parser("reingest", help="Re-ingest a document by ID.")
    p_reingest.add_argument("doc_id", type=int, help="Document numeric ID.")
    p_reingest.set_defaults(func=cmd_reingest)

    # delete
    p_delete = k_sub.add_parser("delete", help="Delete a document by ID.")
    p_delete.add_argument("doc_id", type=int, help="Document numeric ID.")
    p_delete.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
