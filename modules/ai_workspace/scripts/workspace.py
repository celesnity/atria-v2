#!/usr/bin/env python
"""ai_workspace CLI — secure department document workspace.

Every command prints JSON to stdout. Access decisions come from the module's
SQLite DB (the access matrix); document content lives on disk. Upload is
restricted to Manager and above; browsing/opening is filtered per user.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import access  # noqa: E402
import audit  # noqa: E402
import ek_index  # noqa: E402
import repo  # noqa: E402
import storage  # noqa: E402


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _require_user(user_id: str) -> "repo.ResolvedUser":
    user = repo.load_user(user_id)
    if user is None:
        _print({"error": f"unknown user: {user_id}"})
        raise SystemExit(1)
    return user


# --- commands ---------------------------------------------------------------

def cmd_seed() -> int:
    from seed_db import seed  # local import; tools dir on path

    _print(seed())
    return 0


def cmd_initdb() -> int:
    from db import init_db

    init_db()
    _print({"initialized": True})
    return 0


def cmd_login(user_id: str, password: str) -> int:
    user = repo.authenticate(user_id, password)
    if user is None:
        audit.append_event({"type": "login", "user_id": user_id, "ok": False})
        _print({"authenticated": False, "reason": "invalid credentials"})
        return 1
    audit.append_event({"type": "login", "user_id": user_id, "ok": True})
    _print({
        "authenticated": True, "user_id": user.user_id, "full_name": user.full_name,
        "role": user.role, "department": user.department,
        "can_upload": access.can_upload(user.role),
    })
    return 0


def cmd_whoami(user_id: str) -> int:
    user = _require_user(user_id)
    matrix = repo.load_access_matrix()
    _print({
        "user_id": user.user_id, "full_name": user.full_name, "role": user.role,
        "department": user.department, "can_upload": access.can_upload(user.role),
        "accessible_classifications": sorted(
            access.accessible_classifications(user.role, matrix)
        ),
    })
    return 0


def cmd_can_access(user_id: str, doc_id: str) -> int:
    user = _require_user(user_id)
    doc = repo.get_document(doc_id)
    if doc is None:
        _print({"error": f"unknown document: {doc_id}"})
        return 1
    matrix = repo.load_access_matrix()
    decision = access.decide(
        user.role, user.department, doc["classification"], doc["department"], matrix
    )
    audit.append_event({
        "type": "can_access", "user_id": user.user_id, "doc_id": doc_id,
        "decision": "allow" if decision.allowed else "deny",
    })
    _print({
        "user_id": user.user_id, "role": user.role, "department": user.department,
        "doc_id": doc_id, "classification": doc["classification"],
        "department_of_doc": doc["department"], "allowed": decision.allowed,
        "reason": decision.reason,
    })
    return 0


def cmd_folders(user_id: str) -> int:
    user = _require_user(user_id)
    matrix = repo.load_access_matrix()
    docs = repo.list_documents()
    folders = []
    for dept in repo.list_departments():
        code = dept["dept_code"]
        visible = sum(
            1 for d in docs
            if d["department"] == code and access.decide(
                user.role, user.department, d["classification"], code, matrix
            ).allowed
        )
        is_own = code == user.department
        folders.append({
            "dept_code": code, "name_en": dept["name_en"], "name_vi": dept["name_vi"],
            "knowledge_space": dept["knowledge_space"], "visible_count": visible,
            "is_own": is_own,
            # A folder is locked only when the user can see nothing in it — so the
            # Company space stays open to everyone, other departments lock shut.
            "locked": visible == 0,
        })
    _print({"user_id": user.user_id, "role": user.role, "department": user.department,
            "can_upload": access.can_upload(user.role), "folders": folders})
    return 0


def cmd_workspace(user_id: str, department: str | None) -> int:
    user = _require_user(user_id)
    matrix = repo.load_access_matrix()
    docs = repo.list_documents(department)
    visible = [
        {"doc_id": d["doc_id"], "title": d["title"],
         "classification": d["classification"], "department": d["department"],
         "mime_type": d["mime_type"], "size_bytes": d["size_bytes"],
         "uploaded_by_name": d["uploaded_by_name"], "created_at": d["created_at"],
         "original_filename": d["original_filename"]}
        for d in docs
        if access.decide(
            user.role, user.department, d["classification"], d["department"], matrix
        ).allowed
    ]
    audit.append_event({
        "type": "workspace", "user_id": user.user_id, "department": department,
        "visible_doc_ids": [d["doc_id"] for d in visible],
    })
    _print({
        "user_id": user.user_id, "role": user.role, "department": user.department,
        "filter_department": department, "total_visible": len(visible),
        "documents": visible,
    })
    return 0


def cmd_add_document(
    user_id: str,
    file_path: str | None,
    classification: str,
    title: str | None,
    use_stdin: bool = False,
    filename: str | None = None,
    is_base64: bool = False,
    department: str | None = None,
) -> int:
    user = _require_user(user_id)
    if not access.can_upload(user.role):
        audit.append_event({"type": "upload", "user_id": user.user_id, "ok": False,
                             "reason": "not_authorized"})
        _print({"uploaded": False,
                "reason": f"role {user.role} may not upload; Manager+ required"})
        return 1
    if classification not in access.CLASSIFICATIONS:
        _print({"uploaded": False,
                "reason": f"invalid classification: {classification!r}",
                "valid": list(access.CLASSIFICATIONS)})
        return 1

    # Department is the uploader's own by default; only an Executive may target
    # another department.
    target_dept = user.department
    if department and department != user.department:
        if user.role != "Executive":
            _print({"uploaded": False,
                    "reason": "chỉ Executive được tải lên phòng khác"})
            return 1
        if department not in {d["dept_code"] for d in repo.list_departments()}:
            _print({"uploaded": False, "reason": f"phòng không tồn tại: {department}"})
            return 1
        target_dept = department

    import tempfile

    tmp_holder: Path | None = None
    if use_stdin:
        name = filename or "upload.txt"
        raw = sys.stdin.buffer.read()
        if is_base64:
            import base64

            try:
                data = base64.b64decode(raw)
            except (ValueError, TypeError):
                _print({"uploaded": False, "reason": "invalid base64 payload"})
                return 1
        else:
            data = raw
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix="_" + storage.safe_filename(name))
        tmp.write(data)
        tmp.close()
        tmp_holder = Path(tmp.name)
        src = tmp_holder
        src_name = name
    else:
        if not file_path:
            _print({"uploaded": False, "reason": "provide --file or --stdin"})
            return 1
        src = Path(file_path)
        if not src.is_file():
            _print({"uploaded": False, "reason": f"file not found: {file_path}"})
            return 1
        src_name = src.name

    doc_id = repo.next_doc_id()
    doc_title = title or Path(src_name).stem
    rel, size, mime = storage.save_upload(str(src), target_dept, doc_id, filename=src_name)
    if tmp_holder is not None:
        try:
            tmp_holder.unlink()
        except OSError:
            pass

    # Extract text from non-plain-text formats (PDF/DOCX/PPTX/image) into a
    # sidecar so the document is viewable now and embeddable later.
    extracted_chars = 0
    if not storage.is_text(mime, src_name):
        import extract

        try:
            text = extract.extract_text(storage.abs_path(rel), src_name)
        except Exception:  # noqa: BLE001 - accept the file even if parsing fails
            text = ""
        if text:
            storage.write_sidecar(rel, text)
            extracted_chars = len(text)

    repo.insert_document(
        doc_id=doc_id, title=doc_title, dept_code=target_dept,
        classification_code=classification, file_path=rel, original_filename=src_name,
        mime_type=mime, size_bytes=size, uploaded_by=user.user_id,
    )

    # Push into EK for AI search (best-effort; indexing never fails the upload).
    if not storage.is_text(mime, src_name):
        index_text = text  # from the extraction block above (may be "")
    else:
        try:
            index_text = storage.read_text(rel)
        except OSError:
            index_text = ""
    if index_text.strip():
        indexed = ek_index.index_document(
            doc_id=doc_id, title=doc_title, dept_code=target_dept,
            classification=classification, text=index_text, owner=user.user_id,
        )
        index_status = "indexed" if indexed else "failed"
    else:
        index_status = "skipped"
    repo.set_index_status(doc_id, index_status)

    audit.append_event({
        "type": "upload", "user_id": user.user_id, "ok": True, "doc_id": doc_id,
        "department": target_dept, "classification": classification,
        "extracted_chars": extracted_chars, "index_status": index_status,
    })
    _print({
        "uploaded": True, "doc_id": doc_id, "title": doc_title,
        "department": target_dept, "classification": classification,
        "size_bytes": size, "file_path": rel, "extracted_chars": extracted_chars,
        "index_status": index_status,
    })
    return 0


def cmd_delete_document(user_id: str, doc_id: str) -> int:
    """Soft-delete a document. Manager+ within their department (Executive: any)."""
    user = _require_user(user_id)
    doc = repo.get_document(doc_id)
    if doc is None:
        _print({"error": f"unknown document: {doc_id}"})
        return 1
    authorized = access.can_upload(user.role) and (
        user.role == "Executive" or doc["department"] == user.department
    )
    if not authorized:
        audit.append_event({"type": "delete", "user_id": user.user_id, "doc_id": doc_id,
                             "ok": False, "reason": "not_authorized"})
        _print({"deleted": False,
                "reason": "cần Manager+ và đúng phòng (hoặc Executive)"})
        return 1
    repo.set_document_status(doc_id, "deleted")
    ek_index.remove_document(doc_id=doc_id)  # drop chunks from the index (best-effort)
    audit.append_event({"type": "delete", "user_id": user.user_id, "doc_id": doc_id,
                        "ok": True, "department": doc["department"]})
    _print({"deleted": True, "doc_id": doc_id, "department": doc["department"]})
    return 0


def cmd_manage(user_id: str, department: str | None) -> int:
    """Management listing (Manager+): files within scope, with full metadata."""
    user = _require_user(user_id)
    if not access.can_upload(user.role):
        _print({"error": "cần Manager trở lên", "role": user.role})
        return 1
    if user.role == "Executive":
        scope = department  # None → all departments
        manageable = [d["dept_code"] for d in repo.list_departments()]
    else:
        scope = user.department  # Manager/Director: own department only
        manageable = [user.department]
    docs = repo.list_documents(scope)
    _print({
        "user_id": user.user_id, "role": user.role, "department": user.department,
        "scope": scope or "ALL", "manageable_departments": manageable,
        "total": len(docs), "documents": docs,
    })
    return 0


def cmd_stats(user_id: str) -> int:
    """Aggregate counts over the documents the user may access (for the overview)."""
    user = _require_user(user_id)
    matrix = repo.load_access_matrix()
    visible = [
        d for d in repo.list_documents()
        if access.decide(user.role, user.department, d["classification"],
                         d["department"], matrix).allowed
    ]
    by_class: dict[str, int] = {}
    by_dept: dict[str, int] = {}
    for d in visible:
        by_class[d["classification"]] = by_class.get(d["classification"], 0) + 1
        by_dept[d["department"]] = by_dept.get(d["department"], 0) + 1
    _print({
        "user_id": user.user_id, "role": user.role, "department": user.department,
        "total_visible": len(visible), "by_classification": by_class, "by_department": by_dept,
    })
    return 0


def _fill_text_preview(payload: dict, doc: dict) -> None:
    """Populate ``payload`` with an extracted-text preview (fallback path)."""
    mime = doc["mime_type"] or ""
    name = doc["original_filename"] or ""
    payload["render"] = "text"
    sidecar = storage.sidecar_path(doc["file_path"])
    if storage.exists(sidecar):
        payload["content"] = storage.read_text(sidecar)
    elif storage.is_text(mime, name):
        payload["content"] = storage.read_text(doc["file_path"])
    else:
        import extract

        try:
            text = extract.extract_text(storage.abs_path(doc["file_path"]), name)
        except Exception:  # noqa: BLE001
            text = ""
        payload["content"] = text
        if not text:
            payload["note"] = "Không xem trước được nội dung (tệp nhị phân hoặc cần OCR)."


def cmd_read_document(user_id: str, doc_id: str) -> int:
    user = _require_user(user_id)
    doc = repo.get_document(doc_id)
    if doc is None:
        _print({"error": f"unknown document: {doc_id}"})
        return 1
    matrix = repo.load_access_matrix()
    decision = access.decide(
        user.role, user.department, doc["classification"], doc["department"], matrix
    )
    audit.append_event({
        "type": "read_document", "user_id": user.user_id, "doc_id": doc_id,
        "decision": "allow" if decision.allowed else "deny",
    })
    if not decision.allowed:
        _print({"allowed": False, "doc_id": doc_id, "reason": decision.reason})
        return 0
    name = doc["original_filename"] or ""
    mime = doc["mime_type"] or ""
    payload = {
        "allowed": True, "doc_id": doc_id, "title": doc["title"],
        "classification": doc["classification"], "department": doc["department"],
        "mime_type": mime, "original_filename": name, "size_bytes": doc["size_bytes"],
    }
    import base64
    import convert

    is_pdf = mime == "application/pdf" or name.lower().endswith(".pdf")
    is_img = mime.startswith("image/") or name.lower().endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
    )
    render_limit = 12 * 1024 * 1024  # inline-render cap; larger files show text only
    exists = storage.exists(doc["file_path"])

    if (is_pdf or is_img) and doc["size_bytes"] <= render_limit and exists:
        payload["render"] = "pdf" if is_pdf else "image"
        payload["file_b64"] = base64.b64encode(storage.read_bytes(doc["file_path"])).decode()
    elif convert.is_office(name) and exists:
        # Render Word/PowerPoint/Excel faithfully by converting to PDF on demand,
        # caching the result next to the source for instant repeat reads.
        pdf_rel = storage.pdf_cache_path(doc["file_path"])
        pdf = storage.read_bytes(pdf_rel) if storage.exists(pdf_rel) else None
        if pdf is None:
            pdf = convert.to_pdf(storage.abs_path(doc["file_path"]))
            if pdf:
                storage.write_pdf_cache(doc["file_path"], pdf)
        if pdf and len(pdf) <= render_limit:
            payload["render"] = "pdf"
            payload["converted"] = True
            payload["file_b64"] = base64.b64encode(pdf).decode()
        else:
            _fill_text_preview(payload, doc)
    else:
        _fill_text_preview(payload, doc)
    _print(payload)
    return 0


def cmd_audit(limit: int) -> int:
    events = audit.read_events()
    if limit and limit > 0:
        events = events[-limit:]
    _print({"events": events})
    return 0


def cmd_health() -> int:
    out: dict[str, str] = {}
    try:
        n = len(repo.list_departments())
        out["db"] = "ok" if n == 8 else f"warn: {n} departments"
    except Exception as exc:  # noqa: BLE001
        out["db"] = f"error: {exc}"
    try:
        root = storage.uploads_root()
        root.mkdir(parents=True, exist_ok=True)
        out["uploads_dir"] = "ok" if root.is_dir() else "error: not a dir"
    except Exception as exc:  # noqa: BLE001
        out["uploads_dir"] = f"error: {exc}"
    _print(out)
    return 0 if all(v == "ok" for v in out.values()) else 1


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workspace", description="ai_workspace CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="Create + populate the DB and file store.")
    sub.add_parser("initdb", help="Create empty tables.")

    p_login = sub.add_parser("login", help="Authenticate a persona (demo).")
    p_login.add_argument("--user", required=True)
    p_login.add_argument("--password", required=True)

    p_who = sub.add_parser("whoami", help="Show a user's access identity.")
    p_who.add_argument("user_id")

    p_can = sub.add_parser("can-access", help="Allow/Deny + reason for user x document.")
    p_can.add_argument("user_id")
    p_can.add_argument("doc_id")

    p_fold = sub.add_parser("folders", help="Department folder grid for a user.")
    p_fold.add_argument("--user", required=True)

    p_ws = sub.add_parser("workspace", help="Documents a user may access.")
    p_ws.add_argument("--user", required=True)
    p_ws.add_argument("--department", default=None)

    p_add = sub.add_parser("add-document", help="Upload a document (Manager+).")
    p_add.add_argument("--user", required=True)
    p_add.add_argument("--file", default=None, help="Source file path (or use --stdin).")
    p_add.add_argument("--stdin", action="store_true", help="Read file bytes from stdin.")
    p_add.add_argument("--base64", action="store_true", help="Stdin payload is base64-encoded (binary-safe).")
    p_add.add_argument("--filename", default=None, help="Original filename when using --stdin.")
    p_add.add_argument("--classification", required=True)
    p_add.add_argument("--title", default=None)
    p_add.add_argument("--department", default=None,
                       help="Target department (Executive only; else uploader's own).")

    p_read = sub.add_parser("read-document", help="Open a document (access-checked).")
    p_read.add_argument("--user", required=True)
    p_read.add_argument("--doc", required=True)

    p_del = sub.add_parser("delete-document", help="Soft-delete a document (Manager+).")
    p_del.add_argument("--user", required=True)
    p_del.add_argument("--doc", required=True)

    p_manage = sub.add_parser("manage", help="Management listing with metadata (Manager+).")
    p_manage.add_argument("--user", required=True)
    p_manage.add_argument("--department", default=None, help="Executive: filter one department.")

    p_stats = sub.add_parser("stats", help="Accessible-document counts for the overview.")
    p_stats.add_argument("--user", required=True)

    p_audit = sub.add_parser("audit", help="Show recent audit events.")
    p_audit.add_argument("--limit", type=int, default=50)

    sub.add_parser("health", help="Check DB + uploads dir.")
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        return cmd_seed()
    if args.command == "initdb":
        return cmd_initdb()
    if args.command == "login":
        return cmd_login(args.user, args.password)
    if args.command == "whoami":
        return cmd_whoami(args.user_id)
    if args.command == "can-access":
        return cmd_can_access(args.user_id, args.doc_id)
    if args.command == "folders":
        return cmd_folders(args.user)
    if args.command == "workspace":
        return cmd_workspace(args.user, args.department)
    if args.command == "add-document":
        return cmd_add_document(args.user, args.file, args.classification, args.title,
                                use_stdin=args.stdin, filename=args.filename,
                                is_base64=getattr(args, "base64", False),
                                department=args.department)
    if args.command == "read-document":
        return cmd_read_document(args.user, args.doc)
    if args.command == "delete-document":
        return cmd_delete_document(args.user, args.doc)
    if args.command == "manage":
        return cmd_manage(args.user, args.department)
    if args.command == "stats":
        return cmd_stats(args.user)
    if args.command == "audit":
        return cmd_audit(args.limit)
    if args.command == "health":
        return cmd_health()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
