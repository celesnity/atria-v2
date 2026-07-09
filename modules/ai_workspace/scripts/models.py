"""SQLAlchemy 2.0 ORM models for the ai_workspace access database.

Six tables encode the dataset's RBAC model: departments, roles,
classifications, an access_matrix (role x classification -> effect), users, and
document metadata. Document *content* is not stored here — only a path to the
file on disk (see storage.py). The DB is the authority for access decisions.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Module-local declarative base (isolated from the core app's ORM)."""


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    dept_code: Mapped[str] = mapped_column(String(16), unique=True)
    name_en: Mapped[str] = mapped_column(String(64))
    name_vi: Mapped[str] = mapped_column(String(64))
    knowledge_space: Mapped[str] = mapped_column(String(32))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_en: Mapped[str] = mapped_column(String(32), unique=True)
    role_vi: Mapped[str] = mapped_column(String(32))


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    sensitivity_level: Mapped[int] = mapped_column(Integer)


class AccessMatrix(Base):
    __tablename__ = "access_matrix"
    __table_args__ = (UniqueConstraint("role_id", "classification_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    classification_id: Mapped[int] = mapped_column(ForeignKey("classifications.id"))
    effect: Mapped[str] = mapped_column(String(20))  # allow | deny | own_department


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. U001
    full_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(128), default="")
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    status: Mapped[str] = mapped_column(String(16), default="Active")
    password_hash: Mapped[str] = mapped_column(String(255), default="")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # e.g. DOC001
    title: Mapped[str] = mapped_column(String(255))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    classification_id: Mapped[int] = mapped_column(ForeignKey("classifications.id"))
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")  # relative to uploads root
    mime_type: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active")
    # EK index lifecycle: pending | indexed | failed | skipped
    index_status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
