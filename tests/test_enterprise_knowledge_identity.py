# tests/test_enterprise_knowledge_identity.py
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_identity_uut", _MOD / "identity.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_identity_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


_CSV = (
    "user_id,full_name,department,role,email,status\n"
    "U004,Phạm Quốc Dũng,ENG,Employee,user004@synthetic.local,Active\n"
    "U007,Vũ Thị Lan,EXEC,Executive,user007@synthetic.local,Active\n"
)


def test_load_and_resolve(tmp_path):
    ident = _load()
    p = tmp_path / "users.csv"
    p.write_text(_CSV, encoding="utf-8")
    users = ident.load_users(str(p))
    u = ident.resolve(users, "U004")
    assert u.role == "Employee"
    assert u.department == "ENG"


def test_unknown_user_raises(tmp_path):
    ident = _load()
    p = tmp_path / "users.csv"
    p.write_text(_CSV, encoding="utf-8")
    users = ident.load_users(str(p))
    import pytest
    with pytest.raises(ident.UnknownUserError):
        ident.resolve(users, "U999")
