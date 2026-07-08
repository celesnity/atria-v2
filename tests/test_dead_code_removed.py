"""Task 8 verification: unused retrieval modules moved out; token_monitor kept.

These tests are filesystem-based on purpose. Importing the ``retrieval``
package would trigger ``atria.core.context_engineering.__init__`` -> tools ->
web import chain (needs optional heavy deps like uvicorn), which is unrelated
to what this task changed. Checking the package directory + ``__init__`` source
verifies the move without that coupling.
"""

from pathlib import Path

import atria

_RETRIEVAL_DIR = Path(atria.__file__).parent / "core" / "context_engineering" / "retrieval"


def test_token_monitor_kept_in_package():
    assert (_RETRIEVAL_DIR / "token_monitor.py").exists()


def test_dead_retrieval_modules_moved_out():
    assert not (_RETRIEVAL_DIR / "indexer.py").exists()
    assert not (_RETRIEVAL_DIR / "retriever.py").exists()


def test_init_exports_only_token_monitor():
    src = (_RETRIEVAL_DIR / "__init__.py").read_text()
    assert "ContextTokenMonitor" in src
    assert "CodebaseIndexer" not in src
    assert "ContextRetriever" not in src
    assert "EntityExtractor" not in src
