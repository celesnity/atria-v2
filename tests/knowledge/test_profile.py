import pytest

from minder.core.knowledge.profile import ProfileInjector


class FakeRepo:
    def __init__(self, docs):
        self._docs = docs

    async def summaries_for_inject(self, tenant_id, categories):
        return [
            d
            for d in self._docs
            if d["tenant_id"] == tenant_id and d["category"] in categories
        ]


@pytest.mark.asyncio
async def test_block_has_background_and_persona_sections():
    repo = FakeRepo(
        [
            {
                "tenant_id": "t1",
                "category": "company_background",
                "summary": "We sell rockets.",
            },
            {
                "tenant_id": "t1",
                "category": "persona",
                "summary": "You are Rocket Helper.",
            },
        ]
    )
    block = await ProfileInjector(repo).build_profile_block("t1")
    assert "Bối cảnh tổ chức" in block and "We sell rockets." in block
    assert "Vai trò của bạn" in block and "Rocket Helper" in block


@pytest.mark.asyncio
async def test_no_tenant_or_no_docs_yields_empty():
    assert await ProfileInjector(FakeRepo([])).build_profile_block(None) == ""
    assert await ProfileInjector(FakeRepo([])).build_profile_block("t1") == ""


@pytest.mark.asyncio
async def test_truncated_to_cap():
    repo = FakeRepo([{"tenant_id": "t1", "category": "persona", "summary": "x" * 100}])
    block = await ProfileInjector(repo, max_chars=40).build_profile_block("t1")
    assert len(block) <= 41 and block.endswith("…")
