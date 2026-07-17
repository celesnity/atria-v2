"""Scan the mounted seed folder and enqueue new/changed documents."""

from __future__ import annotations

import hashlib
import logging
import os

from minder.core.knowledge.categories import is_valid_category
from minder.core.knowledge.parsing import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


def sha256_file(path: str) -> str:
    """Return the hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


async def scan_seed_dir(root: str, repo) -> list[int]:
    """Enqueue new/changed files under root/<tenant_id>/<category>/<file>.

    Upsert-only: files removed from the folder are never auto-deleted. Returns
    ids of documents newly created (i.e. enqueued for ingest).
    """
    if not os.path.isdir(root):
        return []
    new_ids: list[int] = []
    for tenant_id in sorted(os.listdir(root)):
        tenant_dir = os.path.join(root, tenant_id)
        if not os.path.isdir(tenant_dir):
            continue
        for category in sorted(os.listdir(tenant_dir)):
            cat_dir = os.path.join(tenant_dir, category)
            if not os.path.isdir(cat_dir) or not is_valid_category(category):
                logger.info("seed: skip non-category dir %s/%s", tenant_id, category)
                continue
            for name in sorted(os.listdir(cat_dir)):
                path = os.path.join(cat_dir, name)
                ext = os.path.splitext(name)[1].lower()
                if not os.path.isfile(path) or ext not in SUPPORTED_EXTENSIONS:
                    continue
                content_hash = sha256_file(path)
                if await repo.find_document_by_hash(tenant_id, content_hash):
                    continue
                doc_id = await repo.create_document(
                    tenant_id,
                    category,
                    name,
                    content_hash,
                    source_path=path,
                    source_filename=name,
                )
                new_ids.append(doc_id)
    return new_ids
