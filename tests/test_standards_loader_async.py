import threading
import uuid
from unittest.mock import MagicMock

import pytest

from services.backend.domain.models.standard_chunk import StandardChunk
from services.backend.domain.models.standard_document import StandardDocument
from services.backend.infrastructure.ai.vectorstore.standards_indexer import StandardsVectorIndexer
from services.backend.infrastructure.audit.standards_loader import StandardsLoader
from services.backend.infrastructure.storage.path_resolver import bootstrap_storage, get_storage_root

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """
    In-memory mock store for StandardDocument/StandardChunk, following the same
    pattern used in test_phase4_audit_pipeline.py, so this runs fully offline.
    """
    monkeypatch.setattr(StandardDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardChunk, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    class MockField:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            class Comparison:
                def __init__(self, left, right):
                    self.left = left
                    self.right = right
            return Comparison(self, other)

    StandardDocument.standard_hash = MockField("standard_hash")

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        return self

    async def mock_find_one(cls, *args, **kwargs):
        # Always a brand-new standard, so ingest_standard reaches the vector-indexing step.
        return None

    async def mock_insert_many(cls, documents, *args, **kwargs):
        for doc in documents:
            if not hasattr(doc, "id") or doc.id is None:
                doc.id = uuid.uuid4().hex
        return documents

    monkeypatch.setattr(StandardDocument, "save", mock_save)
    monkeypatch.setattr(StandardDocument, "find_one", classmethod(mock_find_one))
    monkeypatch.setattr(StandardChunk, "insert_many", classmethod(mock_insert_many))


async def test_ingest_standard_offloads_vector_indexing_off_the_event_loop_thread(monkeypatch):
    """
    Audit finding #2 (docs/refactoring-audit-2026-07-23.md): StandardsLoader.ingest_standard must
    run StandardsVectorIndexer.index_standard_chunks() via asyncio.to_thread, not call it directly,
    since embedding generation + LanceDB writes are CPU/IO-bound and would otherwise block the event
    loop for every other concurrent request — the exact problem this same function's file-hash and
    PDF-parsing calls were already offloaded to fix.

    Proof: patch index_standard_chunks to record which OS thread it actually ran on. If it's the
    same thread that's running this async test, the call was NOT offloaded (the bug). If it's a
    different thread, asyncio.to_thread's worker pool handled it (the fix).
    """
    bootstrap_storage()

    main_thread_id = threading.get_ident()
    call_thread_id: dict[str, int] = {}

    def fake_index_standard_chunks(**kwargs):
        call_thread_id["id"] = threading.get_ident()
        return True

    monkeypatch.setattr(
        StandardsVectorIndexer,
        "index_standard_chunks",
        staticmethod(fake_index_standard_chunks),
    )

    content = (
        "# SECTION 1. LAYER CONVENTIONS\n"
        "All structural contours must rest on layer LAYER_BORDER.\n"
    )
    temp_src = get_storage_root() / "standards" / "temp_src_async_offload_test.txt"
    temp_src.parent.mkdir(parents=True, exist_ok=True)
    temp_src.write_text(content, encoding="utf-8")

    try:
        doc, is_duplicate = await StandardsLoader.ingest_standard(
            src_file_path=temp_src,
            name="Async Offload Test Standard",
        )
    finally:
        if temp_src.exists():
            temp_src.unlink()

    assert is_duplicate is False
    assert "id" in call_thread_id, "index_standard_chunks was never called"
    assert call_thread_id["id"] != main_thread_id, (
        "index_standard_chunks ran on the event-loop thread instead of being "
        "offloaded via asyncio.to_thread"
    )
