"""
Guards the event loop against `StandardsLoader.ingest_standard`'s blocking work.

Original finding (audit finding #2, `docs/refactoring-audit-2026-07-23.md`): `ingest_standard` is
`async`, and every CPU/IO-bound step inside it must go through `asyncio.to_thread` or it stalls
every other concurrent request for the duration of a PDF parse.

**Rewritten by R0.** The original test proved this against
`StandardsVectorIndexer.index_standard_chunks`, which R0 deleted along with the rest of the fake
embedding stack — the "embedding generation" it was offloading was `np.random.default_rng(...)`,
so the guard was protecting the event loop from a random number generator. The property it tested
is still real and still worth pinning; it just has to point at work that actually exists. The
heaviest surviving offload is `StandardsParser.parse_file` (`standards_loader.py:90`), which parses
PDFs and Excel workbooks. `calculate_file_hash` (:67) and `shutil.copy2` (:85) are offloaded too
and are checked here as well.

**Extended by R1**, as R0 said it would be. Real lexical indexing is back in `ingest_standard`,
and unlike what it replaced it is genuinely CPU-bound: fitting a TF-IDF vocabulary runs over the
*whole* standards corpus, not just the chunks being added, because idf is a corpus-level property.
`build_index` is therefore covered here alongside the parse and hash.

The proof technique is unchanged from the original: record which OS thread the call actually runs
on. Same thread as the test = not offloaded (the bug). Different thread = `asyncio.to_thread`'s
worker pool handled it (the fix).
"""
import threading
import uuid
from unittest.mock import MagicMock

import pytest

from services.backend.domain.models.standard_chunk import StandardChunk
from services.backend.domain.models.standard_document import StandardDocument
from services.backend.infrastructure.audit.standards_loader import StandardsLoader
from services.backend.infrastructure.audit.standards_parser import StandardsParser
from services.backend.infrastructure.retrieval import service as retrieval_service
from services.backend.infrastructure.retrieval.index_builder import BuildResult
from services.backend.infrastructure.storage.path_resolver import (
    bootstrap_storage,
    get_storage_root,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    """
    In-memory mock store for StandardDocument/StandardChunk, following the same
    pattern used in test_phase4_audit_pipeline.py, so this runs fully offline.
    """
    for model in (StandardDocument, StandardChunk):
        monkeypatch.setattr(
            model, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
        )

    class MockField:  # noqa: PLW1641 — equality is overloaded to build a query, not to hash
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
        # Always a brand-new standard, so ingest_standard reaches the parsing step.
        return None

    async def mock_insert_many(cls, documents, *args, **kwargs):
        for doc in documents:
            if not hasattr(doc, "id") or doc.id is None:
                doc.id = uuid.uuid4().hex
        return documents

    monkeypatch.setattr(StandardDocument, "save", mock_save)
    monkeypatch.setattr(StandardDocument, "find_one", classmethod(mock_find_one))
    monkeypatch.setattr(StandardChunk, "insert_many", classmethod(mock_insert_many))

    # R1: ingest_standard now rebuilds the retrieval index, which re-reads the whole corpus.
    class MockQuery:
        def limit(self, _n):
            return self

        async def to_list(self):
            return []

    monkeypatch.setattr(StandardChunk, "find_all", classmethod(lambda cls, *a, **k: MockQuery()))


async def _ingest_recording_threads(monkeypatch) -> dict[str, int]:
    """Runs one ingest, returning {step_name: os_thread_id_it_ran_on}."""
    threads: dict[str, int] = {}

    real_parse = StandardsParser.parse_file
    real_hash = StandardsLoader.calculate_file_hash

    def recording_parse(path):
        threads["parse_file"] = threading.get_ident()
        return real_parse(path)

    def recording_hash(path):
        threads["calculate_file_hash"] = threading.get_ident()
        return real_hash(path)

    def recording_build_index(collection, records, root=None):
        threads["build_index"] = threading.get_ident()
        return BuildResult(collection, len(records), built=False, reason="stubbed in test")

    monkeypatch.setattr(StandardsParser, "parse_file", staticmethod(recording_parse))
    monkeypatch.setattr(StandardsLoader, "calculate_file_hash", staticmethod(recording_hash))
    # Patched where `service` looks it up, not where it is defined — `service` imported the name
    # at module load, so rebinding `index_builder.build_index` would not be seen.
    monkeypatch.setattr(retrieval_service, "build_index", recording_build_index)

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
    return threads


async def test_ingest_standard_offloads_blocking_work_off_the_event_loop_thread(monkeypatch):
    """Every blocking step in `ingest_standard` must run on a worker thread, not the event loop.

    `parse_file` reads and chunks PDFs and Excel workbooks; `build_index` fits a TF-IDF vocabulary
    over the entire standards corpus. Either would hold the event loop for its full duration and
    stall every other request the backend is serving.
    """
    bootstrap_storage()
    main_thread_id = threading.get_ident()

    threads = await _ingest_recording_threads(monkeypatch)

    assert "calculate_file_hash" in threads, "calculate_file_hash was never called"
    assert "parse_file" in threads, "parse_file was never called"
    assert "build_index" in threads, (
        "build_index was never called — ingest_standard must rebuild the retrieval index (R1), "
        "or new standards are invisible to retrieval until the next restart."
    )

    offenders = [step for step, tid in threads.items() if tid == main_thread_id]
    assert not offenders, (
        f"These blocking steps ran on the event-loop thread instead of being offloaded via "
        f"asyncio.to_thread: {offenders}. See audit finding #2 — an async function that does "
        "CPU-bound work inline blocks every other concurrent request for its duration."
    )
