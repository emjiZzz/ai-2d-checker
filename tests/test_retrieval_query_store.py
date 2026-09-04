"""Stage B — the query store, and the one property that makes it worth having.

A query and a relevance label have different lifetimes. `labels.LabelSet` pins the
`source_digest` of the index it was authored against and refuses to score across a mismatch, so
every label dies the moment the corpus grows. A query does not: "what did a checker ask" is a fact
about the checker, not about the index.

That is the whole reason Stage B can run *before* Stage C and in parallel with more sources
landing — and it only holds if the query store never acquires a corpus dependency. The first test
below is the guard on that.

The second cluster pins the extraction of `build_drawing_keywords` out of
`AuditOrchestrator._retrieve_lessons_learned`. The harvester and production must build the
*same* query: a harvester that built a nearly-identical one would measure something the product
does not do.
"""
from __future__ import annotations

import inspect
import json

import pytest

from services.backend.infrastructure.audit import audit_orchestrator
from services.backend.infrastructure.retrieval.index_builder import build_index
from services.backend.infrastructure.retrieval.labels import LabelError, synthetic_label_set
from services.backend.infrastructure.retrieval.metrics import (
    MIN_QUERIES_FOR_VERDICT,
    QueryOutcome,
    score_retrieval,
)
from services.backend.infrastructure.retrieval.queries import (
    MAX_QUERY_KEYWORDS,
    QueryOrigin,
    QuerySet,
    QueryStoreError,
    RetrievalQuery,
    build_drawing_keywords,
    build_drawing_query,
    drawing_query_text,
)
from services.backend.infrastructure.retrieval.store import Record

#: Shared temp index root for the smoke-label tests. A module-scoped dict rather than a fixture
#: argument so the helpers below read cleanly; populated by `_index_root`.
_TMP: dict = {}


@pytest.fixture(autouse=True)
def _index_root(tmp_path_factory):
    """Every index this module builds goes to a temp root, never the real storage tree."""
    _TMP["root"] = tmp_path_factory.mktemp("retrieval-index")
    yield
    _TMP.clear()


class _Drawing:
    """Duck-typed stand-in. The builder reads two attributes; layers are passed separately."""

    def __init__(self, file_name="M745230A01.dxf", entity_counts=None):
        self.file_name = file_name
        self.entity_counts = entity_counts or {}


# ---------------------------------------------------------------------------
# 1. A query must not acquire a corpus dependency
# ---------------------------------------------------------------------------

def test_a_stored_query_records_no_source_digest_and_no_guideline_version():
    """The property the whole stage rests on.

    If a query ever pins the index it was written against, Stage B stops being runnable ahead of
    Stage C and every corpus rebuild throws away the input that took longest to gather.
    """
    store = QuerySet(collection="standards")
    store.add("does a 12mm plate need a weld symbol callout", QueryOrigin.CHECKER)
    payload = json.dumps(store.to_dict())

    assert "source_digest" not in payload
    assert "guideline_version" not in payload

    fields = set(store.queries[0].to_dict())
    assert fields == {"query_id", "query", "origin", "note", "created_at"}


def test_a_query_set_round_trips_through_disk(tmp_path):
    store = QuerySet(collection="standards")
    store.add("first real question", QueryOrigin.CHECKER, note="asked during the M7452 review")
    store.add("second real question", QueryOrigin.FINDING)

    path = tmp_path / "queries-standards.json"
    store.save(path)
    reloaded = QuerySet.load(path, "standards")

    assert [q.query for q in reloaded.queries] == ["first real question", "second real question"]
    assert reloaded.queries[0].note == "asked during the M7452 review"
    assert reloaded.queries[0].origin is QueryOrigin.CHECKER
    assert reloaded.queries[1].origin is QueryOrigin.FINDING


def test_an_absent_store_is_empty_rather_than_an_error(tmp_path):
    """Nobody has recorded a query yet is normal operation, not a malformed file."""
    store = QuerySet.load(tmp_path / "nope.json", "standards")
    assert store.queries == []
    assert store.collection == "standards"


def test_a_malformed_store_raises_rather_than_reading_as_empty(tmp_path):
    path = tmp_path / "queries-standards.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(QueryStoreError):
        QuerySet.load(path, "standards")


def test_the_same_question_is_not_stored_twice():
    """Two identical questions are one question, and would weight double against the 30 gate."""
    store = QuerySet(collection="standards")
    assert store.add("same question", QueryOrigin.CHECKER) is not None
    assert store.add("  same question  ", QueryOrigin.CHECKER) is None
    assert len(store.queries) == 1


def test_an_empty_query_is_refused():
    store = QuerySet(collection="standards")
    with pytest.raises(QueryStoreError):
        store.add("   ", QueryOrigin.CHECKER)


def test_origin_is_required_and_must_be_one_of_the_known_kinds():
    """Mirrors `labels.Provenance`. A query the system generated and a question a person asked
    are not the same evidence, and the difference disappears if either can be stored untagged."""
    with pytest.raises(QueryStoreError):
        RetrievalQuery.from_dict({"query_id": "q1", "query": "x", "origin": "invented"})
    with pytest.raises(QueryStoreError):
        RetrievalQuery.from_dict({"query_id": "q1", "query": "x"})


# ---------------------------------------------------------------------------
# 2. The harvester and production must build the same query
# ---------------------------------------------------------------------------

def test_the_production_query_is_built_exactly_as_it_was_before_the_extraction():
    """Byte-identical to `_retrieve_lessons_learned`'s inline construction.

    Written out literally rather than recomputed, so this fails if the *format* moves even when
    both callers would still agree with each other. The rules being pinned: layer names upper-
    cased then split on `[_\\-\\s]+` keeping parts longer than 2, entity-type keys lowered, file
    name split on `[_\\-\\s.]+` keeping parts longer than 3, deduplicated in first-seen order,
    capped at 20, joined after the file name.
    """
    drawing = _Drawing(
        file_name="M745230A01_rev_b.dxf",
        entity_counts={"line": 10, "TEXT": 4},
    )
    layers = ["BORDER_LINE", "DIM-TEXT", "AB"]

    assert build_drawing_query(drawing, layers) == (
        "M745230A01_rev_b.dxf border line dim text m745230a01"
    )


def test_layer_names_actually_reach_the_query():
    """The regression guard for the defect this whole fix is about.

    Until 2026-08-17 layer names were read from `drawing.metadata["layers"]`, a key nothing
    writes, so this branch contributed nothing on every drawing in the database and a production
    query was the file name plus a constant. The failure was invisible because a missing key
    yields a *shorter query*, never an error — so the property worth pinning is not "the code
    reads layers" but "a layer name a caller supplies is present in the output".
    See [[Gotcha - The Strongest Signal in the Audit Query Was Never Written]].
    """
    drawing = _Drawing(file_name="x.dxf", entity_counts={"line": 1})

    without = build_drawing_query(drawing, [])
    with_layers = build_drawing_query(drawing, ["HATCH_PATTERN"])

    assert "hatch" not in (without or "")
    assert "hatch" in (with_layers or "")
    assert "pattern" in (with_layers or "")


def test_a_drawing_with_no_usable_keywords_yields_no_query():
    """Matches the orchestrator's skip: no keywords means no retrieval, not an empty search."""
    assert build_drawing_query(_Drawing(file_name="a.dxf")) is None
    assert build_drawing_keywords(_Drawing(file_name="a.dxf")) == []


def test_the_keyword_list_is_capped():
    layers = [f"LAYER{i:03d}" for i in range(40)]
    assert len(build_drawing_keywords(_Drawing(file_name="x.dxf"), layers)) == MAX_QUERY_KEYWORDS


def test_keywords_are_deduplicated_in_first_seen_order():
    drawing = _Drawing(file_name="x.dxf", entity_counts={"text": 1})
    assert build_drawing_keywords(drawing, ["TEXT", "TEXT_BORDER"]) == ["text", "border"]


def test_the_query_text_survives_a_file_name_containing_a_space():
    """The reason `build_drawing_keywords` is separate from `build_drawing_query`.

    The orchestrator needs the keyword list for its MongoDB fallback *and* the joined text for
    the lexical index. Deriving the first by splitting the second on spaces — the obvious
    shortcut — silently corrupts it here.
    """
    drawing = _Drawing(file_name="my drawing.dxf")
    keywords = build_drawing_keywords(drawing, ["BORDER"])

    assert "border" in keywords
    assert "drawing" in keywords
    assert drawing_query_text(drawing.file_name, keywords).startswith("my drawing.dxf ")


def test_the_orchestrator_uses_the_shared_builder_rather_than_its_own_copy():
    """Asserted on the source: the property is *which function is called*, and reaching the real
    one needs a database. Two constructions of the production query would drift while both kept
    working, and the harvest would then measure a query production never issues."""
    raw = inspect.getsource(audit_orchestrator.AuditOrchestrator._retrieve_lessons_learned)
    # Comments stripped: this function *documents* the defect it fixed, and a naive substring
    # check matches that prose and fails on correct code.
    code = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("#")
    )

    assert "build_drawing_keywords" in code
    assert "drawing_query_text" in code
    assert "re.split" not in code, (
        "the orchestrator is rebuilding keywords inline again; that is the copy this "
        "extraction removed"
    )
    assert "layer_names_for" in code, (
        "the orchestrator is not fetching layer names, so the 'strongest signal' branch is "
        "inert again - see the gotcha this fix closed"
    )
    assert 'metadata["layers"]' not in code, (
        "reading the key nothing writes is the defect itself"
    )


# ---------------------------------------------------------------------------
# 3. A harvest is a projection; human input is not
# ---------------------------------------------------------------------------

def test_re_harvesting_replaces_stale_production_queries_and_keeps_human_ones():
    """A production query is derived from the current code, so a harvest must be idempotent.

    When the query construction changes — as it just did — a store that merely appends would
    hold queries production can no longer issue, next to the new ones, with nothing marking
    which is which.
    """
    store = QuerySet(collection="standards")
    store.add("old pipeline query", QueryOrigin.PRODUCTION)
    store.add("a question a checker asked", QueryOrigin.CHECKER)
    store.add("a finding, rephrased", QueryOrigin.FINDING)

    assert store.drop_origin(QueryOrigin.PRODUCTION) == 1
    assert [q.query for q in store.queries] == [
        "a question a checker asked",
        "a finding, rephrased",
    ]


def test_dropping_a_human_origin_is_refused():
    """The asymmetry that makes `QueryOrigin` required in the first place: a pipeline query can
    be regenerated by re-running a tool, and a question a person asked cannot."""
    store = QuerySet(collection="standards")
    store.add("a question a checker asked", QueryOrigin.CHECKER)

    for origin in (QueryOrigin.CHECKER, QueryOrigin.FINDING):
        with pytest.raises(QueryStoreError):
            store.drop_origin(origin)
    assert len(store.queries) == 1


def test_generated_smoke_labels_can_never_be_reported_as_a_measurement():
    """Stage C's dry run. The guideline described this smoke test for months with no
    implementation, so the one cheap check available before labelling could not be run.

    The property that matters is not what it scores but that it *cannot* be mistaken for
    evidence: every label is stamped synthetic, `LabelSet.scored()` excludes them by default,
    and a score that includes them fails the informative gate however good the number is.
    """
    records = [
        Record(id="a1", text="Exit criterion\nthe first stage is done when the set is clean",
               source="Plan", section="Exit criterion"),
        Record(id="a2", text="Risks\nthe corpus may never be labelled at all",
               source="Plan", section="Risks"),
    ]
    build_index("vault", records, root=_TMP["root"])
    label_set = synthetic_label_set("vault", root=_TMP["root"])

    assert [str(lb.provenance) for lb in label_set.labels] == ["synthetic", "synthetic"]
    assert [lb.query for lb in label_set.labels] == ["Exit criterion", "Risks"]
    assert label_set.human_labels() == []
    assert label_set.scored() == [], "synthetic labels must be excluded by default"
    assert len(label_set.scored(include_synthetic=True)) == len(records)
    assert label_set.source_digest, "the set must pin the digest it was generated against"

    # A perfect run over a large corpus: every other gate passes, so the synthetic flag is the
    # only thing that can withhold the verdict. That is what makes this non-vacuous.
    perfect = [
        QueryOutcome(query_id=f"s{i:04d}", retrieved_ids=("a1",), relevant_ids=frozenset({"a1"}))
        for i in range(MIN_QUERIES_FOR_VERDICT + 5)
    ]
    assert score_retrieval(perfect, k=5, corpus_size=989, synthetic_included=False).informative
    assert not score_retrieval(perfect, k=5, corpus_size=989, synthetic_included=True).informative


def test_a_record_with_no_heading_yields_no_smoke_label():
    """Its heading is what becomes the query, and an empty query tests nothing."""
    records = [Record(id="a1", text="body only, long enough to index", source="Note", section=None)]
    build_index("entities", records, root=_TMP["root"])
    assert synthetic_label_set("entities", root=_TMP["root"]).labels == []


def test_generating_smoke_labels_over_an_unusable_index_raises(tmp_path):
    """An unloaded store's `records` property silently yields `[]`, which would make a broken
    index look like a label set of zero labels — a perfect nothing — rather than an error."""
    with pytest.raises(LabelError):
        synthetic_label_set("vault", root=tmp_path)


def test_an_id_is_not_reused_after_a_drop_leaves_a_gap():
    """`add` scans rather than counting. With ids derived from the list length, a store holding
    q002(checker) after q001(production) went would mint a second q002 — two different questions
    at one address, which is the collision `relevant_ids` cannot survive."""
    store = QuerySet(collection="standards")
    store.add("pipeline", QueryOrigin.PRODUCTION)     # q001
    store.add("checker asked this", QueryOrigin.CHECKER)  # q002
    store.drop_origin(QueryOrigin.PRODUCTION)

    store.add("a second real question", QueryOrigin.CHECKER)
    ids = [q.query_id for q in store.queries]
    assert len(ids) == len(set(ids)), f"duplicate query_id after a drop: {ids}"
