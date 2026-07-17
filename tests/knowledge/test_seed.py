import pytest

from minder.core.knowledge.seed import scan_seed_dir


class FakeRepo:
    def __init__(self):
        self.docs = {}
        self.created = []

    async def find_document_by_hash(self, tenant_id, content_hash):
        return self.docs.get((tenant_id, content_hash))

    async def create_document(self, tenant_id, category, title, content_hash, **kw):
        new_id = len(self.created) + 1
        self.docs[(tenant_id, content_hash)] = {"id": new_id}
        self.created.append((tenant_id, category, title, content_hash, kw))
        return new_id


def _seed(tmp_path, tenant, category, name, body):
    d = tmp_path / tenant / category
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f


@pytest.mark.asyncio
async def test_scan_enqueues_valid_files_only(tmp_path):
    _seed(tmp_path, "t1", "reference_docs", "a.md", "hello")
    _seed(tmp_path, "t1", "bad_category", "b.md", "x")  # skipped: bad category
    _seed(tmp_path, "t1", "reference_docs", "c.docx", "x")  # skipped: unsupported
    repo = FakeRepo()
    new_ids = await scan_seed_dir(str(tmp_path), repo)
    assert len(new_ids) == 1
    assert repo.created[0][0:3] == ("t1", "reference_docs", "a.md")


@pytest.mark.asyncio
async def test_scan_is_idempotent_on_unchanged_hash(tmp_path):
    _seed(tmp_path, "t1", "persona", "p.md", "same")
    repo = FakeRepo()
    first = await scan_seed_dir(str(tmp_path), repo)
    second = await scan_seed_dir(str(tmp_path), repo)
    assert len(first) == 1 and second == []
