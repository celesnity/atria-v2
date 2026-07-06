#!/usr/bin/env python
"""enterprise_knowledge CLI — secure, permission-aware knowledge retrieval.

Every retrieval is scoped to the querying user's (role, department): an ACL
filter constrains the vector search, and an independent guard re-checks each hit
before synthesis. Answers are grounded, cited, and Vietnamese.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config  # type: ignore[import-not-found]
from client import RoleClient  # type: ignore[import-not-found]
from corpus import load_corpus  # type: ignore[import-not-found]
from chunking import chunk_document  # type: ignore[import-not-found]
from index_store import IndexStore  # type: ignore[import-not-found]
import identity  # type: ignore[import-not-found]
import acl  # type: ignore[import-not-found]
import audit  # type: ignore[import-not-found]
import graph_store  # type: ignore[import-not-found]
import graph_build  # type: ignore[import-not-found]
import graph_retrieval  # type: ignore[import-not-found]

# Output dim of the embedding model. Default matches OpenAI text-embedding-3-small.
EMBED_DIM = 1536


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _graph_enabled() -> bool:
    """Query-time master switch for GraphRAG (EK_GRAPH_ENABLED, default off)."""
    return _env("EK_GRAPH_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def _samples_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "sample_documents")


def _build_store(embed_fn: Callable | None = None, qdrant: object | None = None) -> IndexStore:
    """Build an IndexStore from EK_QDRANT_URL + a RoleClient index_embed embedder."""
    from qdrant_client import QdrantClient

    if qdrant is None:
        qdrant = QdrantClient(url=_env("EK_QDRANT_URL", "http://localhost:6333"))
    if embed_fn is None:
        rc = RoleClient(load_config())
        embed_fn = lambda texts: rc.embed("index_embed", texts)  # noqa: E731
    store = IndexStore(qdrant, embed_fn)
    store.ensure_collection(dim=int(_env("EK_EMBED_DIM", str(EMBED_DIM))))
    return store


def _synthesis_chat_fn() -> Callable[[list], str]:
    rc = RoleClient(load_config())
    return lambda messages: rc.chat("synthesis", messages)


def _build_graph_store(run_fn: Callable | None = None) -> "graph_store.EKGraphStore":
    """Build an EKGraphStore from EK_NEO4J_* (or an injected run_fn for tests)."""
    if run_fn is None:
        run_fn = graph_store.neo4j_run_fn(graph_store.build_driver())
    return graph_store.EKGraphStore(run_fn)


def _kg_extract_chat_fn() -> Callable[[list], str]:
    rc = RoleClient(load_config())
    return lambda messages: rc.chat("kg_extract", messages)


def guard_accessible(user: "identity.User", hits: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split hits into (accessible, blocked) by re-running the ACL predicate.

    Defence in depth: retrieval is already ACL-filtered, so ``blocked`` should be
    empty; anything here indicates a filter/index mismatch worth auditing.
    """
    safe: list[dict] = []
    blocked: list[dict] = []
    for hit in hits:
        decision = acl.can_access(
            user, {"classification": hit["classification"], "department": hit["department"]}
        )
        (safe if decision.allowed else blocked).append(hit)
    return safe, blocked


def load_doc_meta(samples: str) -> dict[str, dict]:
    """Map doc_id -> {classification, department, title} from the corpus files."""
    meta: dict[str, dict] = {}
    for doc in load_corpus(samples):
        meta[doc.doc_id] = {
            "classification": doc.classification,
            "department": doc.department,
            "title": doc.title,
        }
    return meta


# --- commands ---------------------------------------------------------------


def _cmd_health() -> int:
    cfg = load_config()
    rc = RoleClient(cfg)
    out: dict[str, str] = {}

    def probe(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            out[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - health must never raise
            out[name] = f"error: {exc}"

    probe("index_embed", lambda: rc.embed("index_embed", ["ping"]))
    # A tiny but non-trivial budget: reasoning models (gpt-5/o-series) 400 on a
    # 1-token cap ("could not finish"), so give the probe enough to reply.
    probe(
        "synthesis",
        lambda: rc.chat("synthesis", [{"role": "user", "content": "ping"}], max_tokens=32),
    )

    def qdrant_probe() -> None:
        from qdrant_client import QdrantClient

        QdrantClient(url=_env("EK_QDRANT_URL", "http://localhost:6333")).get_collections()

    probe("qdrant", qdrant_probe)

    def neo4j_probe() -> None:
        driver = graph_store.build_driver()
        try:
            graph_store.neo4j_run_fn(driver)("RETURN 1 AS ok", {})
        finally:
            driver.close()

    probe("neo4j", neo4j_probe)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if all(v == "ok" for v in out.values()) else 1


def _cmd_ingest(samples: str) -> int:
    store = _build_store()
    docs = load_corpus(samples)
    total = 0
    for doc in docs:
        total += store.upsert_chunks(chunk_document(doc))
    print(json.dumps({"documents": len(docs), "chunks": total}, indent=2))
    return 0


def _resolve_user(user_id: str, users_path: str | None) -> "identity.User":
    users = identity.load_users(users_path or identity.default_users_path())
    return identity.resolve(users, user_id)


def _augment_with_graph(
    text: str, user: "identity.User", hits: list[dict], k: int, graph_store_obj: object | None
) -> list[dict]:
    """Expand ``hits`` with ACL-safe graph neighbors; fall back to ``hits`` on error."""
    try:
        gs = graph_store_obj or _build_graph_store()
        hops = int(_env("EK_GRAPH_HOPS", "1"))
        max_neighbors = int(_env("EK_GRAPH_MAX_NEIGHBORS", "20"))
        graph_hits = graph_retrieval.expand(gs, hits, user, hops, max_neighbors)
        merged = graph_retrieval.merge_hits(hits, graph_hits, cap=max(k, len(hits)))
        safe, _blocked = guard_accessible(user, merged)  # belt-and-suspenders re-check
        return safe
    except Exception as exc:  # noqa: BLE001 - graph is optional; never fail the query
        print(f"[graph] disabled for this query: {exc}", file=sys.stderr)
        return hits


def _cmd_query(
    text: str,
    user_id: str,
    k: int,
    department: str | None,
    synthesize: bool,
    users_path: str | None,
    store: IndexStore | None = None,
    graph: bool = False,
    graph_store_obj: object | None = None,
) -> int:
    user = _resolve_user(user_id, users_path)
    if store is None:
        store = _build_store()
    hits = store.query(text, k=k, acl_filter=acl.build_filter(user), department=department)
    hits, blocked = guard_accessible(user, hits)
    if graph and _graph_enabled():
        hits = _augment_with_graph(text, user, hits, k, graph_store_obj)
    payload: dict[str, object] = {
        "query": text,
        "user": {"user_id": user.user_id, "role": user.role, "department": user.department},
        "hits": hits,
    }
    if not hits:
        payload["message"] = "Không tìm thấy tài liệu phù hợp trong phạm vi truy cập của bạn."
    if synthesize and hits:
        from synthesis import synthesize as _synth  # local import

        answer = _synth(text, hits, _synthesis_chat_fn())
        payload["answer"] = answer
    audit.append_event(
        {
            "type": "query",
            "user_id": user.user_id,
            "role": user.role,
            "department": user.department,
            "query": text,
            "returned_doc_ids": sorted({h["doc_id"] for h in hits}),
            "blocked_doc_ids": sorted({h["doc_id"] for h in blocked}),
        }
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_whoami(user_id: str, users_path: str | None) -> int:
    user = _resolve_user(user_id, users_path)
    print(
        json.dumps(
            {
                "user_id": user.user_id,
                "full_name": user.full_name,
                "role": user.role,
                "department": user.department,
                "accessible_classifications": sorted(acl.accessible_classifications(user)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_can_access(user_id: str, doc_id: str, users_path: str | None, samples: str) -> int:
    user = _resolve_user(user_id, users_path)
    meta = load_doc_meta(samples)
    if doc_id not in meta:
        print(json.dumps({"error": f"unknown doc_id: {doc_id}"}, indent=2))
        return 1
    decision = acl.can_access(user, meta[doc_id])
    print(
        json.dumps(
            {
                "user_id": user.user_id,
                "role": user.role,
                "department": user.department,
                "doc_id": doc_id,
                "classification": meta[doc_id]["classification"],
                "department_of_doc": meta[doc_id]["department"],
                "allowed": decision.allowed,
                "reason": decision.reason,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    audit.append_event(
        {
            "type": "can_access",
            "user_id": user.user_id,
            "doc_id": doc_id,
            "permission_decision": "allow" if decision.allowed else "deny",
        }
    )
    return 0


def _cmd_list() -> int:
    print(json.dumps(_build_store().list_indexed(), indent=2, ensure_ascii=False))
    return 0


def _cmd_reset() -> int:
    _build_store().reset()
    print(json.dumps({"reset": True}, indent=2))
    return 0


def _cmd_audit(limit: int) -> int:
    events = audit.read_events()
    if limit and limit > 0:
        events = events[-limit:]
    print(json.dumps({"events": events}, indent=2, ensure_ascii=False))
    return 0


def _cmd_graph_build(samples: str, extract: bool) -> int:
    store = _build_graph_store()
    store.ensure_constraints()
    docs = load_corpus(samples)
    stats = graph_build.build_backbone(store, docs, chunk_document)
    if extract:
        cache = graph_build.ExtractionCache(
            str(Path(__file__).resolve().parent.parent / "data" / "graph_extract_cache.json")
        )
        stats["extraction"] = graph_build.build_extraction(
            store, docs, chunk_document, _kg_extract_chat_fn(), cache
        )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


def _cmd_graph_stats() -> int:
    print(json.dumps(_build_graph_store().stats(), indent=2, ensure_ascii=False))
    return 0


def _cmd_graph_reset() -> int:
    _build_graph_store().reset()
    print(json.dumps({"reset": True}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="knowledge", description="Enterprise Knowledge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Check embeddings + synthesis + Qdrant reachability.")

    p_ingest = sub.add_parser("ingest", help="Parse + chunk + index sample_documents/.")
    p_ingest.add_argument("--samples", default=None)

    p_query = sub.add_parser("query", help="Permission-aware retrieval for a question.")
    p_query.add_argument("text")
    p_query.add_argument("--user", required=True, help="Querying user_id (RBAC scope).")
    p_query.add_argument("--k", type=int, default=5)
    p_query.add_argument(
        "--department", default=None, help="Narrow within accessible scope (canonical id)."
    )
    p_query.add_argument("--synthesize", action="store_true")
    p_query.add_argument("--users", default=None, help="Path to users.csv override.")
    p_query.add_argument(
        "--graph", action="store_true", help="Expand retrieval with the knowledge graph (GraphRAG)."
    )

    p_who = sub.add_parser("whoami", help="Show a user's resolved access identity.")
    p_who.add_argument("user_id")
    p_who.add_argument("--users", default=None)

    p_can = sub.add_parser("can-access", help="Allow/Deny + reason for a user × document.")
    p_can.add_argument("user_id")
    p_can.add_argument("doc_id")
    p_can.add_argument("--users", default=None)
    p_can.add_argument("--samples", default=None)

    sub.add_parser("list", help="Show index stats.")
    sub.add_parser("reset", help="Delete the index collection.")
    p_audit = sub.add_parser("audit", help="Show recent audit events.")
    p_audit.add_argument("--limit", type=int, default=50)

    p_graph = sub.add_parser("graph", help="Knowledge-graph build/inspect (GraphRAG).")
    gsub = p_graph.add_subparsers(dest="graph_command", required=True)
    g_build = gsub.add_parser("build", help="Build backbone (+ optional LLM extraction).")
    g_build.add_argument("--samples", default=None)
    g_build.add_argument(
        "--extract", action="store_true", help="Also run the LLM entity/relation pass."
    )
    gsub.add_parser("stats", help="Show graph node/edge counts.")
    gsub.add_parser("reset", help="Delete all EK graph nodes.")
    return parser


def _force_utf8_output() -> None:
    """Force UTF-8 on stdout/stderr so Vietnamese output survives legacy consoles.

    On Windows ``sys.stdout`` binds to the console code page (e.g. cp1252),
    which cannot encode Vietnamese diacritics; ``json.dumps(..., ensure_ascii=
    False)`` then raises UnicodeEncodeError. Reconfiguring to UTF-8 keeps output
    human-readable on every platform. No-op where a stream cannot be
    reconfigured (e.g. a captured buffer under pytest).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # pragma: no cover - platform dependent
            pass


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` pairs from ``.env`` text, ignoring comments/blanks.

    Handles an optional ``export`` prefix and strips one layer of surrounding
    single or double quotes. The first ``=`` separates key from value, so values
    containing ``=`` (URLs, query strings) survive intact.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if key:
            out[key] = value.strip().strip('"').strip("'")
    return out


def _load_dotenv() -> None:
    """Populate the environment from the nearest ``.env`` without overriding.

    The CLI is usually run as a bare script (``python knowledge.py ...``) with no
    shell export step, so provider keys and ``EK_*`` overrides live in the repo's
    ``.env``. Values already in the environment win, so an explicit export still
    takes precedence. Skipped under pytest to keep unit tests hermetic.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    for parent in Path(__file__).resolve().parents:
        env_file = parent / ".env"
        if env_file.is_file():
            for key, value in _parse_dotenv(
                env_file.read_text(encoding="utf-8", errors="ignore")
            ).items():
                os.environ.setdefault(key, value)
            return


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    _force_utf8_output()
    _load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "health":
            return _cmd_health()
        if args.command == "ingest":
            return _cmd_ingest(args.samples or _samples_dir())
        if args.command == "query":
            return _cmd_query(
                args.text,
                args.user,
                args.k,
                args.department,
                args.synthesize,
                args.users,
                graph=args.graph,
            )
        if args.command == "whoami":
            return _cmd_whoami(args.user_id, args.users)
        if args.command == "can-access":
            return _cmd_can_access(
                args.user_id, args.doc_id, args.users, args.samples or _samples_dir()
            )
        if args.command == "list":
            return _cmd_list()
        if args.command == "reset":
            return _cmd_reset()
        if args.command == "audit":
            return _cmd_audit(args.limit)
        if args.command == "graph":
            if args.graph_command == "build":
                return _cmd_graph_build(args.samples or _samples_dir(), args.extract)
            if args.graph_command == "stats":
                return _cmd_graph_stats()
            if args.graph_command == "reset":
                return _cmd_graph_reset()
            return 2
        return 2
    except identity.UnknownUserError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
