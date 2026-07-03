from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_corpus_uut", _MOD / "corpus.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_corpus_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


_DOC = """---
doc_id: DOC007
title: Khung lương tham khảo
department: HR
classification: Confidential
owner: HR
knowledge_space: Department Knowledge
last_updated: 2025-08-22
language: vi
---
# Khung lương tham khảo
Nội dung mật của phòng Nhân sự.
"""


def test_parse_document_reads_frontmatter(tmp_path):
    c = _load()
    p = tmp_path / "DOC007.md"
    p.write_text(_DOC, encoding="utf-8")
    doc = c.parse_document(str(p))
    assert doc.doc_id == "DOC007"
    assert doc.department == "HR"
    assert doc.classification == "Confidential"
    assert doc.text.startswith("# Khung lương")


def test_missing_required_key_raises(tmp_path):
    c = _load()
    p = tmp_path / "bad.md"
    p.write_text("---\ntitle: x\n---\nbody\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        c.parse_document(str(p))


def test_knowledge_space_derived_when_absent(tmp_path):
    c = _load()
    body = "---\ndoc_id: DOC001\ntitle: t\ndepartment: COMP\nclassification: Public\n---\nx\n"
    p = tmp_path / "DOC001.md"
    p.write_text(body, encoding="utf-8")
    doc = c.parse_document(str(p))
    assert doc.knowledge_space == "Company Knowledge"
