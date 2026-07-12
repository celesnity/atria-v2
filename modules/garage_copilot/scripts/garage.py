"""garage_copilot RAG CLI — workshop-manual retrieval for the KTV repair copilot.

Thin, garage-configured front over the enterprise_knowledge retrieval library
(design D6 revised): same chunking/index/synthesis stack, but its own corpus
directory (``sample_manuals/``), its own Qdrant collection, and NO access
control — the garage corpus is open to every technician in v1, so every query
runs unfiltered (``acl_filter=None``).

Commands:
    python garage.py health                 # embeddings + synthesis + Qdrant probes
    python garage.py ingest [--dir DIR]     # parse + chunk + index sample_manuals/
    python garage.py query "câu hỏi" [--k 5] [--mode hybrid] [--synthesize]

Model/provider config is shared with enterprise_knowledge (``EK_<ROLE>_<FIELD>``
env vars, ``EK_QDRANT_URL``); garage-specific knobs are ``GARAGE_QDRANT_COLLECTION``
(default ``garage_chunks``) and ``GARAGE_CORPUS_DIR``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

_HERE = Path(__file__).resolve().parent
_MODULE_ROOT = _HERE.parent
_EK_SCRIPTS = _MODULE_ROOT.parent / "enterprise_knowledge" / "scripts"

EMBED_DIM = 1536
DEFAULT_COLLECTION = "garage_chunks"


def _load_ek_bootstrap() -> ModuleType:
    """Load enterprise_knowledge's collision-proof sibling loader by file path."""
    key = "_garage_ek_bootstrap"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, _EK_SCRIPTS / "_bootstrap.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load enterprise_knowledge bootstrap from {_EK_SCRIPTS}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def ek(name: str) -> ModuleType:
    """Import an enterprise_knowledge script as a library (namespaced, collision-proof)."""
    return _load_ek_bootstrap().sibling(name)


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default) or default


def collection_name() -> str:
    return _env("GARAGE_QDRANT_COLLECTION", DEFAULT_COLLECTION)


def corpus_dir() -> str:
    return _env("GARAGE_CORPUS_DIR", str(_MODULE_ROOT / "sample_manuals"))


def audit_path() -> str:
    return str(_MODULE_ROOT / "data" / "audit.log.jsonl")


def _build_store(embed_fn: Callable | None = None, qdrant: object | None = None):
    """IndexStore on the garage collection, from EK_QDRANT_URL + index_embed role."""
    index_store = ek("index_store")
    if qdrant is None:
        from qdrant_client import QdrantClient

        qdrant = QdrantClient(
            url=_env("EK_QDRANT_URL", "http://localhost:6333"),
            api_key=_env("EK_QDRANT_API_KEY", "") or None,
        )
    if embed_fn is None:
        client = ek("client")
        config = ek("config")
        rc = client.RoleClient(config.load_config())
        embed_fn = lambda texts: rc.embed("index_embed", texts)  # noqa: E731
    store = index_store.IndexStore(qdrant, embed_fn, collection=collection_name())
    store.ensure_collection(dim=int(_env("EK_EMBED_DIM", str(EMBED_DIM))))
    return store


def _synthesis_chat_fn() -> Callable[[list], str]:
    client = ek("client")
    config = ek("config")
    rc = client.RoleClient(config.load_config())
    return lambda messages: rc.chat("synthesis", messages)


def _cmd_health() -> int:
    """Probe embeddings, synthesis, and Qdrant. No neo4j — garage has no GraphRAG."""
    client = ek("client")
    config = ek("config")
    rc = client.RoleClient(config.load_config())
    out: dict[str, str] = {}

    def probe(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            out[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - health must never raise
            out[name] = f"error: {exc}"

    probe("index_embed", lambda: rc.embed("index_embed", ["ping"]))
    probe(
        "synthesis",
        lambda: rc.chat("synthesis", [{"role": "user", "content": "ping"}], max_tokens=32),
    )

    def qdrant_probe() -> None:
        from qdrant_client import QdrantClient

        QdrantClient(
            url=_env("EK_QDRANT_URL", "http://localhost:6333"),
            api_key=_env("EK_QDRANT_API_KEY", "") or None,
        ).get_collections()

    probe("qdrant", qdrant_probe)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if all(v == "ok" for v in out.values()) else 1


def _cmd_ingest(samples: str, store=None) -> int:
    corpus = ek("corpus")
    chunking = ek("chunking")
    bm25 = ek("bm25")
    if store is None:
        store = _build_store()
    docs = corpus.load_corpus(samples)
    records: list = []
    for doc in docs:
        records.extend(chunking.chunk_document(doc))
    avgdl = bm25.average_length([r.text for r in records])
    total = store.upsert_chunks(records, avgdl=avgdl)
    print(json.dumps({"documents": len(docs), "chunks": total}, indent=2))
    return 0


def _cmd_query(text: str, k: int, synthesize: bool, mode: str, store=None) -> int:
    audit = ek("audit")
    if store is None:
        store = _build_store()
    # Open access by design: garage v1 has no RBAC, every KTV sees the whole corpus.
    hits = store.query(text, k=k, acl_filter=None, mode=mode)
    payload: dict[str, object] = {"query": text, "hits": hits}
    if not hits:
        payload["message"] = (
            "Không tìm thấy nội dung phù hợp trong tài liệu xưởng. "
            "Đừng trả lời dựa trên kiến thức chưa kiểm chứng mà không ghi rõ nhãn."
        )
    if synthesize and hits:
        synthesis = ek("synthesis")
        payload["answer"] = synthesis.synthesize(text, hits, _synthesis_chat_fn())
    audit.append_event(
        {
            "type": "query",
            "module": "garage_copilot",
            "query": text,
            "returned_doc_ids": sorted({h["doc_id"] for h in hits}),
        },
        path=audit_path(),
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` pairs from ``.env`` text, ignoring comments/blanks.

    Copied from enterprise_knowledge's knowledge.py (its copy is not cleanly
    importable in-process — ``from _bootstrap import sibling`` needs the EK
    scripts dir on sys.path). Handles an optional ``export`` prefix and strips
    one layer of quotes; the first ``=`` separates key from value.
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

    Walks up from this file, so a worktree without its own ``.env`` still finds
    the main workspace's. Values already exported win. Skipped under pytest to
    keep unit tests hermetic.
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="garage.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health", help="Check embeddings + synthesis + Qdrant reachability.")
    p_ingest = sub.add_parser("ingest", help="Parse + chunk + index the manual corpus.")
    p_ingest.add_argument("--dir", default=None, help="Corpus dir (default sample_manuals/).")
    p_query = sub.add_parser("query", help="Retrieve cited passages for a question.")
    p_query.add_argument("text")
    p_query.add_argument("--k", type=int, default=5)
    p_query.add_argument("--mode", choices=("dense", "bm25", "hybrid"), default="hybrid")
    p_query.add_argument("--synthesize", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    if args.cmd == "health":
        return _cmd_health()
    if args.cmd == "ingest":
        return _cmd_ingest(args.dir or corpus_dir())
    if args.cmd == "query":
        return _cmd_query(args.text, args.k, args.synthesize, args.mode)
    return 2  # pragma: no cover - argparse enforces choices


if __name__ == "__main__":
    raise SystemExit(main())
