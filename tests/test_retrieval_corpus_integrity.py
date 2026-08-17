"""The corpus the retrieval gate is measured against must be what is actually retrievable.

Two defects of the same shape, found together on 2026-08-14 while checking a claim that the
`standards` corpus held 32 documents.

**It held 16.** The other 16 were the chunks of a standard that had been *deleted* from Mongo,
still being served by an index nothing ever rebuilt. `tests/test_standards_delete_reindex.py`
already pins that `delete_standard` calls `rebuild_standards_index` — that is the first line of
defence and it exists. What was missing is the second: when that rebuild does not take effect
(it is deliberately non-fatal and merely logged), nothing repaired the index afterwards.
`bootstrap_retrieval_indexes` ran at every startup and skipped every collection whose *files were
present*, which is true of a stale index by definition. So `INDEX_SCHEMA_VERSION` was inert —
`search()` reported STALE and no code path anywhere acted on it.

**And the duplication was invisible to the metric.** `corpus_size` in `metrics.py` is
`manifest.n_records`, and the chance floor a verdict is gated on is `k/N` over that count. Sixteen
texts counted twice read as chance 0.16 at k=5, which passes `MAX_CHANCE_FLOOR`; the honest floor
over 16 distinct answers is 0.31, which fails it. A corpus reported itself as able to support a
measurement because it was double-counting a deleted document.

Both are the house failure mode: not an error, a plausible number. See
`Gotcha - A Stale Index Kept Answering For a Deleted Standard`.
"""

from __future__ import annotations

import json

import pytest

from services.backend.infrastructure import retrieval
from services.backend.infrastructure.retrieval import service
from services.backend.infrastructure.retrieval.index_builder import BuildResult
from services.backend.infrastructure.retrieval.metrics import (
    MAX_CHANCE_FLOOR,
    chance_recall_at_k,
)
from services.backend.infrastructure.retrieval.store import INDEX_SCHEMA_VERSION, IndexStatus

# Two distinct clauses, and a third record whose text is byte-identical to the first while
# citing a different source — the shape a deleted-then-reindexed standard leaves behind.
_ROUGHNESS = "表面粗さ surface roughness Ra 3.2 finish symbol"
_WELDING = "溶接記号 welding symbols fillet weld throat thickness"


def _records() -> list[retrieval.Record]:
    return [
        retrieval.Record(id="a1", text=_ROUGHNESS, source="KEMCO AND JIS", section="ROUGHNESS"),
        retrieval.Record(id="b1", text=_WELDING, source="KEMCO AND JIS", section="WELDING"),
        retrieval.Record(id="a2", text=_ROUGHNESS, source="DELETED STANDARD", section="ROUGHNESS"),
    ]


# ---------------------------------------------------------------------------
# The count the gate is computed over
# ---------------------------------------------------------------------------

def test_identical_texts_collapse_to_one_record(tmp_path):
    result = retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)

    assert result.built
    assert result.n_records == 2, "three records holding two distinct texts is a corpus of two"
    assert result.n_duplicates_dropped == 1


def test_the_first_occurrence_is_the_one_kept(tmp_path):
    """Deterministic, and the earliest record keeps the citation."""
    retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)

    store = retrieval.store_for(retrieval.STANDARDS, tmp_path)
    store.load()
    sources = [r.source for r in store.records]

    assert sources == ["KEMCO AND JIS", "KEMCO AND JIS"]
    assert "DELETED STANDARD" not in sources


def test_the_drop_is_reported_rather_than_swallowed(tmp_path, caplog):
    """A duplicate here is a bug upstream. The net has to say what it caught."""
    with caplog.at_level("WARNING"):
        retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)

    logged = caplog.text
    assert "DELETED STANDARD" in logged and "KEMCO AND JIS" in logged, (
        "both citations must appear, or the drop cannot be traced back to its source"
    )


def test_a_deduplicated_corpus_reports_the_chance_floor_that_is_true(tmp_path):
    """The whole reason the count matters: it is the denominator of the gate.

    This is the arithmetic that made a 16-document corpus look like it could support a verdict.
    """
    duplicated = _records() * 8       # 24 records, 16 of them copies
    result = retrieval.build_index(retrieval.STANDARDS, duplicated, root=tmp_path)

    assert result.n_records == 2

    inflated = chance_recall_at_k(len(duplicated), k=5)
    honest = chance_recall_at_k(result.n_records, k=5)
    assert inflated < honest, "double-counting always flatters the floor"
    assert inflated <= MAX_CHANCE_FLOOR < honest, (
        "the inflated count passes the gate the honest one fails — which is exactly how a corpus "
        "too small to measure reports itself as measurable"
    )


def test_records_with_the_same_text_are_never_both_retrievable(tmp_path):
    """The ranking consequence: duplicates score identically and take adjacent slots."""
    retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)

    outcome = retrieval.query("表面粗さ", root=tmp_path, top_k=5)
    texts = [hit.record.text for hit in outcome.hits]

    assert outcome.answered
    assert len(texts) == len(set(texts)), (
        "a top-k holding the same text twice returns fewer answers than it claims"
    )


# ---------------------------------------------------------------------------
# A stale index must be repaired, not merely detected
# ---------------------------------------------------------------------------

def _downgrade_to_v1(root, collection: str) -> None:
    """Make an index look like one written before the current schema."""
    path = retrieval.store_for(collection, root).manifest_path
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["schema_version"] = INDEX_SCHEMA_VERSION - 1
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_an_index_from_an_older_schema_reports_stale(tmp_path):
    retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)
    _downgrade_to_v1(tmp_path, retrieval.STANDARDS)

    store = retrieval.store_for(retrieval.STANDARDS, tmp_path)
    assert store.load() is IndexStatus.STALE
    assert store.exists(), (
        "the whole trap: the files are present, so any check based on presence sees nothing wrong"
    )


@pytest.fixture
def stub_builders(monkeypatch):
    """Replace the three rebuilds with recorders. No Mongo, no vault."""
    called: list[str] = []

    def _recorder(collection: str):
        async def _rebuild(root=None):
            called.append(collection)
            return BuildResult(collection, 1, built=True)
        return _rebuild

    monkeypatch.setattr(service, "rebuild_standards_index", _recorder(retrieval.STANDARDS))
    monkeypatch.setattr(service, "rebuild_domain_rules_index", _recorder(retrieval.DOMAIN_RULES))
    monkeypatch.setattr(service, "rebuild_lessons_index", _recorder(retrieval.LESSONS))
    return called


async def test_startup_rebuilds_a_stale_index(tmp_path, stub_builders):
    """The defect: four days of serving a deleted standard's chunks.

    `bootstrap_retrieval_indexes` gated on `store.exists()`, which a stale index satisfies. The
    version guard could detect the problem and nothing could fix it.
    """
    retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)
    _downgrade_to_v1(tmp_path, retrieval.STANDARDS)

    await service.bootstrap_retrieval_indexes(root=tmp_path)

    assert retrieval.STANDARDS in stub_builders, (
        "a stale index was left in place at startup; INDEX_SCHEMA_VERSION cannot migrate an "
        "install if nothing acts on the status it sets"
    )


async def test_startup_leaves_a_usable_index_alone(tmp_path, stub_builders):
    """The other half — a restart must not pay for a rebuild it does not need."""
    retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)

    await service.bootstrap_retrieval_indexes(root=tmp_path)

    assert retrieval.STANDARDS not in stub_builders
    # The two absent collections are the control: they are MISSING, so they must be built.
    assert retrieval.DOMAIN_RULES in stub_builders and retrieval.LESSONS in stub_builders
