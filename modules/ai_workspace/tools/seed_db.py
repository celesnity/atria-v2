#!/usr/bin/env python
"""Seed the ai_workspace SQLite DB + file store from the dataset.

Populates all six tables (departments, roles, classifications, access_matrix,
users, documents) and copies each seeded document's content file into the
uploads store. Idempotent: drops and recreates the schema on every run.

The reference tables are dataset constants; users come from
``access/users.csv`` and documents from ``access/documents.csv`` +
``access/seed_documents/<id>.md``. Passwords are all the demo value 12345678
(stored hashed).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_MODULE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MODULE / "scripts"))

import access  # noqa: E402
import models  # noqa: E402
import storage  # noqa: E402
from db import reset_db, session_scope  # noqa: E402
from repo import hash_password  # noqa: E402

DEMO_PASSWORD = "12345678"

DEPARTMENTS = [
    (1, "COMP", "Company", "Công ty", "Company Knowledge"),
    (2, "HR", "Human Resources", "Nhân sự", "Department Knowledge"),
    (3, "FIN", "Finance", "Tài chính", "Department Knowledge"),
    (4, "PROD", "Product", "Sản phẩm", "Department Knowledge"),
    (5, "ENG", "Engineering", "Kỹ thuật", "Department Knowledge"),
    (6, "OPS", "Operations", "Vận hành", "Department Knowledge"),
    (7, "LEGAL", "Legal & Compliance", "Pháp chế & Tuân thủ", "Department Knowledge"),
    (8, "EXEC", "Executive Office", "Ban Điều hành", "Executive Knowledge"),
]
ROLES = [
    (1, "Employee", "Nhân viên"),
    (2, "Manager", "Quản lý"),
    (3, "Director", "Giám đốc"),
    (4, "Executive", "Ban Điều hành"),
]
CLASSIFICATIONS = [
    (1, "Public", 1),
    (2, "Internal", 2),
    (3, "Confidential", 3),
    (4, "Restricted", 4),
]


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def seed(db_path: str | None = None, access_dir: Path | None = None) -> dict:
    """(Re)create and populate the DB + file store. Returns row counts."""
    access_dir = access_dir or (_MODULE / "access")
    reset_db(db_path)

    role_id = {r[1]: r[0] for r in ROLES}
    class_id = {c[1]: c[0] for c in CLASSIFICATIONS}
    dept_id = {d[1]: d[0] for d in DEPARTMENTS}

    with session_scope(db_path) as s:
        s.add_all(models.Department(id=i, dept_code=c, name_en=en, name_vi=vi, knowledge_space=ks)
                  for (i, c, en, vi, ks) in DEPARTMENTS)
        s.add_all(models.Role(id=i, role_en=en, role_vi=vi) for (i, en, vi) in ROLES)
        s.add_all(models.Classification(id=i, code=c, sensitivity_level=lvl)
                  for (i, c, lvl) in CLASSIFICATIONS)
        # access_matrix: one row per (role, classification) from the canonical rules
        mid = 1
        for r_en, r_id in role_id.items():
            for c_code, c_id in class_id.items():
                s.add(models.AccessMatrix(
                    id=mid, role_id=r_id, classification_id=c_id,
                    effect=access.DEFAULT_MATRIX[(r_en, c_code)],
                ))
                mid += 1

    # users
    users = _read_csv(access_dir / "users.csv")
    pw_hash = hash_password(DEMO_PASSWORD)
    with session_scope(db_path) as s:
        for u in users:
            if u["department"] not in dept_id or u["role"] not in role_id:
                raise ValueError(f"user {u['user_id']} has bad dept/role: {u}")
            s.add(models.User(
                id=u["user_id"], full_name=u.get("full_name", ""),
                email=u.get("email", ""), role_id=role_id[u["role"]],
                department_id=dept_id[u["department"]], status=u.get("status", "Active"),
                password_hash=pw_hash,
            ))

    # documents: metadata row + copy content file into uploads store
    docs = _read_csv(access_dir / "documents.csv")
    seed_docs = access_dir / "seed_documents"
    with session_scope(db_path) as s:
        for d in docs:
            if d["department"] not in dept_id or d["classification"] not in class_id:
                raise ValueError(f"doc {d['document_id']} has bad dept/class: {d}")
            src = seed_docs / f"{d['document_id']}.md"
            rel, size, mime = storage.save_upload(
                str(src), d["department"], d["document_id"], filename=f"{d['document_id']}.md"
            )
            s.add(models.Document(
                id=d["document_id"], title=d["title"],
                department_id=dept_id[d["department"]],
                classification_id=class_id[d["classification"]],
                original_filename=f"{d['document_id']}.md", file_path=rel,
                mime_type=mime, size_bytes=size, uploaded_by=None, status="active",
            ))

    return {
        "departments": len(DEPARTMENTS), "roles": len(ROLES),
        "classifications": len(CLASSIFICATIONS), "access_matrix": len(ROLES) * len(CLASSIFICATIONS),
        "users": len(users), "documents": len(docs),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed_db", description="Seed ai_workspace DB")
    parser.add_argument("--db", default=None, help="DB path override (else AIW_DB_PATH/default).")
    args = parser.parse_args(argv)
    counts = seed(args.db)
    import json

    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
