"""Work-log store, extractor, and search — the vibe-repairing flywheel.

The conversation IS the work log. On session close, an LLM extraction turns
the transcript into a structured WorkLogRecord (Vietnamese narrative with
English technical terms verbatim; the reported symptom always verbatim as
spoken). Records are stored as JSON (one file per session, under
``GARAGE_WORKLOG_DIR`` — defaults to ``$ATRIA_DIR/garage/worklogs``, falling
back to this module's ``data/worklogs``) and embedded into their own Qdrant
collection (``garage_worklogs``) so the next technician can find them by
paraphrased symptom.

Commands:
    python worklog.py extract --transcript FILE --session-id ID --ro RO \
        --vin VIN --brand BRAND [--technician NAME] [--incomplete]
    python worklog.py search "câu hỏi" [--k 5] [--vin VIN] [--brand BRAND]
    python worklog.py get SESSION_ID
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional

_HERE = Path(__file__).resolve().parent
_MODULE_ROOT = _HERE.parent
_EK_SCRIPTS = _MODULE_ROOT.parent / "enterprise_knowledge" / "scripts"

EMBED_DIM = 1536
WORKLOG_COLLECTION_DEFAULT = "garage_worklogs"

# Required WorkLogRecord fields and their types (design data model).
_REQUIRED_FIELDS: dict[str, type] = {
    "session_id": str,
    "ro_number": str,
    "vin": str,
    "brand": str,
    "symptom_reported": str,
    "hypotheses": list,
    "diagnostic_steps": list,
    "root_cause": str,
    "fix_applied": str,
    "parts_used": list,
    "tools_used": list,
    "citations": list,
    "status": str,
    "language": str,
}

_EXTRACTION_SYSTEM_PROMPT = (
    "Bạn trích xuất nhật ký công việc (work log) có cấu trúc từ hội thoại giữa "
    "kỹ thuật viên và copilot sửa xe. Trả về DUY NHẤT một JSON object với các "
    "khóa: symptom_reported (nguyên văn lời khách hàng/kỹ thuật viên mô tả triệu "
    "chứng — giữ đúng nguyên văn, không dịch), hypotheses (mảng "
    "{hypothesis, outcome: confirmed|rejected|untested, evidence}, bao gồm cả "
    "các giả thuyết đã bị loại), diagnostic_steps (mảng {step, result, citation} "
    "— citation là mã đoạn tài liệu nếu có, ví dụ WSM-RR-2040#2), root_cause, "
    "fix_applied, parts_used (mảng mã phụ tùng), tools_used (mảng), citations "
    "(mảng mọi mã trích dẫn xuất hiện), language. Viết nội dung bằng tiếng Việt, "
    "giữ nguyên thuật ngữ kỹ thuật tiếng Anh (CV axle, torque...). Nếu hội thoại "
    "chưa đi đến kết luận, để root_cause/fix_applied là chuỗi rỗng. Không thêm "
    "khóa nào khác, không giải thích gì ngoài JSON."
)


def _load_ek_bootstrap() -> ModuleType:
    key = "_garage_worklog_ek_bootstrap"
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
    """Import an enterprise_knowledge script as a library (collision-proof)."""
    return _load_ek_bootstrap().sibling(name)


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default) or default


def worklog_dir() -> Path:
    """Resolve the JSON store directory (never committed — runtime data)."""
    explicit = os.environ.get("GARAGE_WORKLOG_DIR")
    if explicit:
        return Path(explicit)
    atria_dir = os.environ.get("ATRIA_DIR")
    if atria_dir:
        return Path(atria_dir) / "garage" / "worklogs"
    return _MODULE_ROOT / "data" / "worklogs"


def collection_name() -> str:
    return _env("GARAGE_WORKLOG_COLLECTION", WORKLOG_COLLECTION_DEFAULT)


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------


def validate_record(record: dict) -> list[str]:
    """Return a list of schema problems; empty when the record is valid."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record is not an object"]
    for field, typ in _REQUIRED_FIELDS.items():
        if field not in record:
            errors.append(f"missing field: {field}")
        elif not isinstance(record[field], typ):
            errors.append(f"wrong type for {field}: expected {typ.__name__}")
    for i, h in enumerate(record.get("hypotheses") or []):
        if not isinstance(h, dict) or "hypothesis" not in h or "outcome" not in h:
            errors.append(f"hypotheses[{i}] must have hypothesis and outcome")
    for i, s in enumerate(record.get("diagnostic_steps") or []):
        if not isinstance(s, dict) or "step" not in s:
            errors.append(f"diagnostic_steps[{i}] must have step")
    if record.get("status") not in (None, "complete", "incomplete"):
        errors.append("status must be complete or incomplete")
    return errors


def parse_llm_json(text: str) -> Optional[dict]:
    """Parse a JSON object out of an LLM reply (handles ``` fences)."""
    if not text:
        return None
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    candidate = fence.group(1) if fence else stripped
    if not candidate.startswith("{"):
        brace = candidate.find("{")
        if brace == -1:
            return None
        candidate = candidate[brace : candidate.rfind("}") + 1]
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def build_extraction_messages(transcript: str, anchor: dict) -> list[dict]:
    user = (
        f"Repair Order: {anchor.get('ro_number', '')} · VIN: {anchor.get('vin', '')} · "
        f"Hãng: {anchor.get('brand', '')}\n\nHội thoại:\n{transcript}"
    )
    return [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fallback_record(anchor: dict) -> dict:
    """A minimal, schema-valid record for failed extractions."""
    return {
        "session_id": str(anchor.get("session_id", "")),
        "ro_number": str(anchor.get("ro_number", "")),
        "vin": str(anchor.get("vin", "")),
        "brand": str(anchor.get("brand", "")),
        "technician": str(anchor.get("technician", "") or ""),
        "symptom_reported": "",
        "hypotheses": [],
        "diagnostic_steps": [],
        "root_cause": "",
        "fix_applied": "",
        "parts_used": [],
        "tools_used": [],
        "citations": [],
        "status": "incomplete",
        "language": "vi",
        "created_at": _now_iso(),
        "extraction_error": "LLM extraction failed schema validation",
    }


def extract_record(
    transcript: str,
    anchor: dict,
    chat_fn: Callable[[list], str],
    incomplete: bool = False,
    max_attempts: int = 2,
) -> dict:
    """Extract a WorkLogRecord from a transcript via the LLM.

    Anchor fields (session/RO/VIN/brand/technician) are stamped from the
    session, never trusted from the LLM. Invalid output is retried once; a
    persistent failure yields a schema-valid ``incomplete`` fallback record so
    the session always has a log.
    """
    messages = build_extraction_messages(transcript, anchor)
    for attempt in range(max_attempts):
        try:
            reply = chat_fn(messages)
        except Exception:  # noqa: BLE001 - LLM outage → fallback record
            break
        parsed = parse_llm_json(reply)
        if parsed is None:
            continue
        record = {
            **parsed,
            "session_id": str(anchor.get("session_id", "")),
            "ro_number": str(anchor.get("ro_number", "")),
            "vin": str(anchor.get("vin", "")),
            "brand": str(anchor.get("brand", "")),
            "technician": str(anchor.get("technician", "") or ""),
            "status": "incomplete" if incomplete else "complete",
            "created_at": _now_iso(),
        }
        record.setdefault("language", "vi")
        if not validate_record(record):
            return record
    return _fallback_record(anchor)


# --------------------------------------------------------------------------
# JSON store
# --------------------------------------------------------------------------


def save_record_json(record: dict) -> str:
    """Write the record to the JSON store; returns the file path."""
    directory = worklog_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['session_id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_record_json(session_id: str) -> Optional[dict]:
    path = worklog_dir() / f"{session_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Embedding index (reuses the EK stack; own collection)
# --------------------------------------------------------------------------


def record_search_text(record: dict) -> str:
    """The embedded text: what the next technician would search for."""
    hypo = "; ".join(
        f"{h.get('hypothesis', '')} ({h.get('outcome', '')})"
        for h in record.get("hypotheses") or []
    )
    return (
        f"{record.get('symptom_reported', '')}\n"
        f"Nguyên nhân: {record.get('root_cause', '')}\n"
        f"Khắc phục: {record.get('fix_applied', '')}\n"
        f"Giả thuyết: {hypo}"
    )


def record_to_chunk(record: dict):
    """Map a WorkLogRecord onto EK's ChunkRecord for indexing.

    ``department`` carries the brand so the store's department filter doubles
    as a brand filter; ``doc_id`` is the session id for JSON-store lookback.
    """
    chunking = ek("chunking")
    text = record_search_text(record)
    return chunking.ChunkRecord(
        doc_id=str(record["session_id"]),
        chunk_id=f"WL-{record['session_id']}#0",
        text=text,
        start_index=0,
        end_index=len(text),
        token_count=max(1, len(text) // 4),
        title=record.get("symptom_reported", "")[:120],
        department=record.get("brand", ""),
        classification="worklog",
        knowledge_space="Garage Work Logs",
        owner=record.get("technician", ""),
        source_path=str(worklog_dir() / f"{record['session_id']}.json"),
        citation=f"WL-{record['session_id']}#0",
    )


def _build_store(embed_fn: Callable | None = None, qdrant: object | None = None):
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


def index_record(record: dict, store=None) -> int:
    bm25 = ek("bm25")
    if store is None:
        store = _build_store()
    chunk = record_to_chunk(record)
    avgdl = bm25.average_length([chunk.text])
    return store.upsert_chunks([chunk], avgdl=avgdl)


def search_records(
    query: str,
    k: int = 5,
    vin: Optional[str] = None,
    brand: Optional[str] = None,
    store=None,
) -> list[dict]:
    """Paraphrase search over stored work logs, with optional VIN/brand filters.

    Returns summary dicts (full record fields + retrieval score), newest-rank
    first. VIN filtering happens post-retrieval against the JSON store — VIN
    is not an indexed payload field.
    """
    if store is None:
        store = _build_store()
    hits = store.query(query, k=max(k * 2, k), acl_filter=None, department=brand, mode="hybrid")
    results: list[dict] = []
    for hit in hits:
        record = load_record_json(str(hit.get("doc_id", "")))
        if record is None:
            continue
        if vin and record.get("vin") != vin:
            continue
        results.append({**record, "score": hit.get("score")})
        if len(results) >= k:
            break
    return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _synthesis_chat_fn() -> Callable[[list], str]:
    client = ek("client")
    config = ek("config")
    rc = client.RoleClient(config.load_config())
    return lambda messages: rc.chat("synthesis", messages)


def _parse_dotenv(text: str) -> dict[str, str]:
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


def _cmd_extract(args: argparse.Namespace) -> int:
    transcript = Path(args.transcript).read_text(encoding="utf-8")
    anchor = {
        "session_id": args.session_id,
        "ro_number": args.ro,
        "vin": args.vin,
        "brand": args.brand,
        "technician": args.technician or "",
    }
    record = extract_record(transcript, anchor, _synthesis_chat_fn(), incomplete=args.incomplete)
    path = save_record_json(record)
    indexed = 0
    try:
        indexed = index_record(record)
    except Exception as exc:  # noqa: BLE001 - index failure must not lose the JSON
        print(json.dumps({"warning": f"index failed: {exc}"}), file=sys.stderr)
    print(
        json.dumps(
            {"saved": path, "indexed": indexed, "status": record["status"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    results = search_records(args.text, k=args.k, vin=args.vin, brand=args.brand)
    print(json.dumps({"query": args.text, "results": results}, ensure_ascii=False, indent=2))
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    record = load_record_json(args.session_id)
    if record is None:
        print(json.dumps({"error": f"no work log for session {args.session_id}"}))
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="worklog.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ext = sub.add_parser("extract", help="Extract + save + index a work log from a transcript.")
    p_ext.add_argument("--transcript", required=True, help="Path to the transcript text file.")
    p_ext.add_argument("--session-id", required=True)
    p_ext.add_argument("--ro", required=True)
    p_ext.add_argument("--vin", required=True)
    p_ext.add_argument("--brand", required=True)
    p_ext.add_argument("--technician", default="")
    p_ext.add_argument(
        "--incomplete",
        action="store_true",
        help="Mark the log incomplete (abandoned session sweep).",
    )
    p_search = sub.add_parser("search", help="Paraphrase search over stored work logs.")
    p_search.add_argument("text")
    p_search.add_argument("--k", type=int, default=5)
    p_search.add_argument("--vin", default=None)
    p_search.add_argument("--brand", default=None)
    p_get = sub.add_parser("get", help="Fetch one work log by session id.")
    p_get.add_argument("session_id")
    return ap


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    if args.cmd == "extract":
        return _cmd_extract(args)
    if args.cmd == "search":
        return _cmd_search(args)
    if args.cmd == "get":
        return _cmd_get(args)
    return 2  # pragma: no cover - argparse enforces choices


if __name__ == "__main__":
    raise SystemExit(main())
