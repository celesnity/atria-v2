"""Repository helpers — the only place that reads/writes the access DB.

Returns plain dataclasses/dicts (never live ORM instances) so callers are
insulated from the session lifecycle. Also holds password hashing for the
module-level demo login.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

import models  # noqa: E402
from db import session_scope  # noqa: E402


# --- password hashing (stdlib pbkdf2, no extra deps) ------------------------


def hash_password(password: str, salt: bytes | None = None, iterations: int = 100_000) -> str:
    """Return a ``pbkdf2$iterations$salt$hash`` string for ``password``."""
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify ``password`` against a stored pbkdf2 string."""
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# --- resolved identity ------------------------------------------------------


@dataclass(frozen=True)
class ResolvedUser:
    """A user resolved to the values access decisions need."""

    user_id: str
    full_name: str
    role: str  # role_en
    department: str  # dept_code
    department_id: int
    status: str


def _resolve(session, user: "models.User") -> ResolvedUser:
    role = session.get(models.Role, user.role_id)
    dept = session.get(models.Department, user.department_id)
    return ResolvedUser(
        user_id=user.id,
        full_name=user.full_name,
        role=role.role_en,
        department=dept.dept_code,
        department_id=dept.id,
        status=user.status,
    )


def load_user(user_id: str, path: str | None = None) -> ResolvedUser | None:
    """Resolve a user id to a :class:`ResolvedUser`, or ``None`` if unknown."""
    with session_scope(path) as session:
        user = session.get(models.User, user_id)
        return _resolve(session, user) if user else None


def authenticate(user_id: str, password: str, path: str | None = None) -> ResolvedUser | None:
    """Return the resolved user iff the password matches; else ``None``."""
    with session_scope(path) as session:
        user = session.get(models.User, user_id)
        if not user or not verify_password(password, user.password_hash):
            return None
        return _resolve(session, user)


def load_access_matrix(path: str | None = None) -> dict[tuple[str, str], str]:
    """Load the access matrix keyed ``(role_en, classification_code) -> effect``."""
    out: dict[tuple[str, str], str] = {}
    with session_scope(path) as session:
        roles = {r.id: r.role_en for r in session.scalars(select(models.Role))}
        classes = {c.id: c.code for c in session.scalars(select(models.Classification))}
        for am in session.scalars(select(models.AccessMatrix)):
            out[(roles[am.role_id], classes[am.classification_id])] = am.effect
    return out


def _doc_dict(session, doc, classes, depts, users) -> dict:
    """Project a Document ORM row into a metadata dict (no live ORM leak)."""
    return {
        "doc_id": doc.id,
        "title": doc.title,
        "classification": classes[doc.classification_id],
        "department": depts[doc.department_id],
        "file_path": doc.file_path,
        "mime_type": doc.mime_type,
        "original_filename": doc.original_filename,
        "size_bytes": doc.size_bytes,
        "uploaded_by": doc.uploaded_by,
        "uploaded_by_name": users.get(doc.uploaded_by, "Hệ thống"),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "status": doc.status,
        "index_status": doc.index_status,
    }


def _lookup_maps(session):
    classes = {c.id: c.code for c in session.scalars(select(models.Classification))}
    depts = {d.id: d.dept_code for d in session.scalars(select(models.Department))}
    users = {u.id: u.full_name for u in session.scalars(select(models.User))}
    return classes, depts, users


def get_document(doc_id: str, path: str | None = None) -> dict | None:
    """Return a document metadata dict, or ``None`` if unknown."""
    with session_scope(path) as session:
        doc = session.get(models.Document, doc_id)
        if not doc:
            return None
        classes, depts, users = _lookup_maps(session)
        return _doc_dict(session, doc, classes, depts, users)


def set_document_status(doc_id: str, status: str, path: str | None = None) -> bool:
    """Update a document's status (e.g. soft-delete). Returns False if unknown."""
    with session_scope(path) as session:
        doc = session.get(models.Document, doc_id)
        if not doc:
            return False
        doc.status = status
        return True


def set_index_status(doc_id: str, status: str, path: str | None = None) -> bool:
    """Update a document's EK ``index_status``. Returns False if the doc is unknown."""
    with session_scope(path) as session:
        doc = session.get(models.Document, doc_id)
        if not doc:
            return False
        doc.index_status = status
        return True


def list_documents(
    department: str | None = None,
    path: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    """List documents (optionally one department) as metadata dicts.

    By default only ``active`` documents are returned; soft-deleted rows are
    hidden unless ``include_deleted`` is set.
    """
    with session_scope(path) as session:
        classes, depts, users = _lookup_maps(session)
        out: list[dict] = []
        for doc in session.scalars(select(models.Document)):
            if not include_deleted and doc.status != "active":
                continue
            if department and depts[doc.department_id] != department:
                continue
            out.append(_doc_dict(session, doc, classes, depts, users))
        return out


def list_departments(path: str | None = None) -> list[dict]:
    """Return all departments as ``{id, dept_code, name_en, name_vi}`` dicts."""
    with session_scope(path) as session:
        return [
            {
                "id": d.id,
                "dept_code": d.dept_code,
                "name_en": d.name_en,
                "name_vi": d.name_vi,
                "knowledge_space": d.knowledge_space,
            }
            for d in session.scalars(select(models.Department).order_by(models.Department.id))
        ]


def next_doc_id(path: str | None = None) -> str:
    """Compute the next ``DOCnnn`` id from existing rows."""
    with session_scope(path) as session:
        ids = [d.id for d in session.scalars(select(models.Document))]
    nums = [int(i[3:]) for i in ids if i.startswith("DOC") and i[3:].isdigit()]
    return f"DOC{(max(nums) + 1) if nums else 1:03d}"


def insert_document(
    doc_id: str,
    title: str,
    dept_code: str,
    classification_code: str,
    file_path: str,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
    uploaded_by: str | None,
    path: str | None = None,
) -> None:
    """Insert a new document metadata row."""
    with session_scope(path) as session:
        dept = session.scalar(
            select(models.Department).where(models.Department.dept_code == dept_code)
        )
        cls = session.scalar(
            select(models.Classification).where(models.Classification.code == classification_code)
        )
        session.add(
            models.Document(
                id=doc_id,
                title=title,
                department_id=dept.id,
                classification_id=cls.id,
                original_filename=original_filename,
                file_path=file_path,
                mime_type=mime_type,
                size_bytes=size_bytes,
                uploaded_by=uploaded_by,
                status="active",
            )
        )
