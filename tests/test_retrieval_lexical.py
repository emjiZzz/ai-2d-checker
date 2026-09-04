"""R1 — the lexical retrieval package.

Covers the stage's exit criterion directly: `retrieval.query(text)` returns ranked chunks with
scores and citations, offline, in <100 ms, with zero non-local sockets — the socket guard being
`infrastructure/eval/runner.py`'s `no_network`, reused rather than reimplemented so "offline" has
one definition in this repo.

The other half of these tests is about the failure mode R0 exists to prevent. An index that is
missing, empty, or built by a different encoder must be *distinguishable* from an index that
searched and found nothing relevant. Several tests here assert on `SearchOutcome.status` for
precisely that reason: `[]` with `status=OK` and `[]` with `status=MISSING` are different answers
and the caller is entitled to tell them apart.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from services.backend.infrastructure import retrieval
from services.backend.infrastructure.eval.runner import no_network
from services.backend.infrastructure.retrieval.store import INDEX_SCHEMA_VERSION

# Mixed Japanese/ASCII, as the real corpus is. `ユニットNo.` is a real title-block field taken
# from the vault's own example, and is the case char n-grams exist to handle.
CORPUS = [
    ("jis-0405", "公差 tolerance general machining dimensions ±0.1 mm", "JIS B 0405", "TOLERANCES"),
    ("jis-0601", "表面粗さ surface roughness Ra 3.2 finish symbol", "JIS B 0601", "ROUGHNESS"),
    ("client-tb", "ユニットNo. 品番 unit number title block field", "Client Rules", "TITLE BLOCK"),
    ("jis-3021", "溶接記号 welding symbols fillet weld throat thickness", "JIS Z 3021", "WELDING"),
    ("jis-0001", "図面 drawing sheet sizes A0 A1 A2 A3 A4 layout", "JIS B 0001", "SHEETS"),
]


def _records() -> list[retrieval.Record]:
    return [
        retrieval.Record(id=rid, text=text, source=source, section=section)
        for rid, text, source, section in CORPUS
    ]


@pytest.fixture
def built_index(tmp_path):
    """A real index on disk, in a temp root. No database, no network, no vault."""
    result = retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path)
    assert result.built and result.n_records == len(CORPUS)
    return tmp_path


# ---------------------------------------------------------------------------
# Exit criterion
# ---------------------------------------------------------------------------

def test_query_returns_ranked_chunks_with_scores_and_citations(built_index):
    """The R1 exit criterion, stated as a test."""
    outcome = retrieval.query("公差 tolerance", root=built_index, top_k=3)

    assert outcome.answered
    assert outcome.hits, "a query sharing several n-grams with a chunk must return it"

    top = outcome.hits[0]
    assert top.record.source == "JIS B 0405"
    assert top.rank == 1
    assert 0.0 < top.score <= 1.0, "cosine over L2-normalised vectors is bounded"
    assert top.record.citation() == "JIS B 0405 > TOLERANCES"

    ranks = [h.rank for h in outcome.hits]
    scores = [h.score for h in outcome.hits]
    assert ranks == sorted(ranks), "ranks are 1..n in order"
    assert scores == sorted(scores, reverse=True), "scores descend"


def test_query_is_offline(built_index):
    """Zero non-local sockets, enforced rather than claimed.

    Reuses `no_network` from the eval runner: the same guard that makes the corpus numbers
    trustworthy should be what makes this claim, so there is one definition of "offline".
    """
    with no_network():
        outcome = retrieval.query("welding 溶接", root=built_index)
    assert outcome.answered
    assert outcome.hits


def test_query_is_under_the_hundred_millisecond_budget(built_index):
    """<100 ms is the stated budget. Brute force is linear, so this is the canary for growth."""
    retrieval.query("warm up the encoder load", root=built_index)  # exclude first-call I/O

    started = time.perf_counter()
    retrieval.query("公差 tolerance surface roughness", root=built_index)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert elapsed_ms < retrieval.SLOW_QUERY_MS, (
        f"query took {elapsed_ms:.1f} ms against a {retrieval.SLOW_QUERY_MS:.0f} ms budget"
    )


def test_char_ngrams_match_across_a_japanese_spacing_difference(built_index):
    """`ユニット No` must find `ユニットNo.` — the reason char n-grams were chosen.

    Japanese does not word-segment on whitespace, so a word tokeniser sees these as unrelated
    tokens. Char n-grams share most of their 2-4 grams and rank it first.
    """
    outcome = retrieval.query("ユニット No", root=built_index, top_k=3)

    assert outcome.hits, "spacing variation must not defeat retrieval"
    assert outcome.hits[0].record.id == "client-tb"


def test_an_unrelated_query_returns_nothing_but_still_answered(built_index):
    """The honest empty: the index searched, and nothing was relevant."""
    outcome = retrieval.query("zzzzz qqqqq", root=built_index)

    assert outcome.hits == []
    assert outcome.status is retrieval.IndexStatus.OK
    assert outcome.answered, "this is a real answer, not a broken index"


# ---------------------------------------------------------------------------
# The R1 risk: an unusable index must not look like an empty result
# ---------------------------------------------------------------------------

def test_missing_index_is_distinguishable_from_no_results(tmp_path):
    """The stage's named risk. `[]` from a missing index is not the same answer as `[]`."""
    outcome = retrieval.query("anything at all", root=tmp_path)

    assert outcome.hits == []
    assert outcome.status is retrieval.IndexStatus.MISSING
    assert not outcome.answered
    assert "not been built" in outcome.detail


def test_building_with_no_records_declines_rather_than_writing_an_empty_index(tmp_path):
    """"Nothing to index" is not the same claim as "indexed, and it was empty"."""
    result = retrieval.build_index(retrieval.STANDARDS, [], root=tmp_path)

    assert not result.built
    assert result.reason == "no records"
    assert not retrieval.store_for(retrieval.STANDARDS, tmp_path).exists()


def test_index_built_by_another_encoder_is_refused_as_stale(built_index):
    """A manifest naming a different encoder means the vectors are not comparable."""
    store = retrieval.store_for(retrieval.STANDARDS, built_index)
    manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    manifest["encoder_name"] = "some-future-dense-encoder-v9"
    store.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    outcome = store.search(
        query_vector=csr_matrix(np.ones((1, 4))),
        expected_encoder="tfidf-char_wb-2_4-v1",
    )

    assert outcome.status is retrieval.IndexStatus.STALE
    assert not outcome.answered


def test_index_from_an_older_schema_version_is_refused(built_index):
    store = retrieval.store_for(retrieval.STANDARDS, built_index)
    manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = INDEX_SCHEMA_VERSION - 1
    store.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert store.load() is retrieval.IndexStatus.STALE


def test_vector_and_record_counts_must_agree(tmp_path):
    """Vectors and records are paired positionally; a mismatch returns the wrong chunk."""
    store = retrieval.store_for(retrieval.STANDARDS, tmp_path)

    with pytest.raises(ValueError, match="positionally paired"):
        store.write(
            matrix=csr_matrix(np.ones((2, 3))),
            records=_records()[:3],
            encoder_name="tfidf-char_wb-2_4-v1",
        )


# ---------------------------------------------------------------------------
# The encoder must never fabricate a vector
# ---------------------------------------------------------------------------

def test_encoder_refuses_to_encode_before_being_fitted():
    """Must raise, not return zeros.

    A zero vector ranks every document equally, which looks exactly like a working search.
    """
    with pytest.raises(retrieval.EncoderError, match="before fit"):
        retrieval.TfidfEncoder().encode(["公差"])


def test_encoder_refuses_to_fit_on_an_empty_corpus():
    with pytest.raises(retrieval.EncoderError, match="zero non-empty texts"):
        retrieval.TfidfEncoder().fit(["", "   ", "\n"])


def test_encoded_vectors_are_l2_normalised():
    """The store treats cosine as a dot product, which is only valid if rows are unit length."""
    encoder = retrieval.TfidfEncoder().fit([t for _, t, _, _ in CORPUS])
    matrix = encoder.encode([t for _, t, _, _ in CORPUS])

    norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=1)).ravel())
    assert np.allclose(norms, 1.0, atol=1e-9)


def test_encoding_is_deterministic():
    """Same text, same vector. The predecessor was deterministic too — and meaningless."""
    texts = [t for _, t, _, _ in CORPUS]
    encoder = retrieval.TfidfEncoder().fit(texts)

    first = encoder.encode(["公差 tolerance"]).toarray()
    second = encoder.encode(["公差 tolerance"]).toarray()
    assert np.array_equal(first, second)


def test_different_texts_produce_different_vectors():
    """Guards the specific shape of the deleted defect from the other side.

    Hash-seeded noise also produced distinct, stable, normalised vectors — so distinctness alone
    proves nothing. What matters is that similarity tracks *shared characters*: two texts about
    tolerance must be closer to each other than either is to one about welding.
    """
    texts = [t for _, t, _, _ in CORPUS]
    encoder = retrieval.TfidfEncoder().fit(texts)

    tol_a = encoder.encode(["公差 tolerance machining"])
    tol_b = encoder.encode(["tolerance dimensions 公差"])
    welding = encoder.encode(["溶接記号 welding fillet"])

    same_topic = (tol_a @ tol_b.T).toarray()[0][0]
    cross_topic = (tol_a @ welding.T).toarray()[0][0]

    assert same_topic > cross_topic, (
        "similarity must follow shared content. A hash-based 'embedding' would fail this while "
        "passing every determinism and normalisation check above."
    )


# ---------------------------------------------------------------------------
# BM25 and fusion
# ---------------------------------------------------------------------------

def test_bm25_ranks_the_relevant_document_first():
    texts = [t for _, t, _, _ in CORPUS]
    welding_idx = [rid for rid, *_ in CORPUS].index("jis-3021")

    scores = retrieval.BM25().fit(texts).scores("溶接 welding fillet")

    assert int(np.argmax(scores)) == welding_idx
    assert scores[welding_idx] > 0


def test_bm25_scores_are_non_negative():
    """The +1 smoothing exists so a term appearing in every document contributes ~0, not < 0."""
    texts = [t for _, t, _, _ in CORPUS]
    bm25 = retrieval.BM25().fit(texts)
    assert (bm25.scores("図面 drawing tolerance") >= 0).all()


def test_char_ngrams_do_not_span_word_boundaries():
    """`char_wb` pads each word and slides inside it. Reproduced locally, so pin the behaviour."""
    tokens = retrieval.char_ngrams("ab cd", ngram_range=(2, 2))
    assert "bc" not in tokens, "an n-gram must not bridge two words"
    assert " a" in tokens and "ab" in tokens


def test_reciprocal_rank_fusion_rewards_agreement():
    """A document ranked well by both rankers must beat one ranked first by only one."""
    fused = dict(retrieval.reciprocal_rank_fusion([1, 2, 3], [2, 1, 3]))
    assert fused[2] > fused[3] and fused[1] > fused[3]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def test_markdown_is_chunked_by_heading_with_the_heading_kept_in_the_text():
    note = (
        "# TOLERANCES\n"
        "General machining tolerance is plus or minus 0.1 mm for all untoleranced dimensions.\n"
        "\n"
        "# WELDING\n"
        "Fillet weld throat thickness must be specified on every welded joint in the assembly.\n"
    )
    records = retrieval.chunk_markdown_by_heading(note, source="Client Rules")

    assert [r.section for r in records] == ["TOLERANCES", "WELDING"]
    assert records[0].text.startswith("TOLERANCES")
    assert "0.1 mm" in records[0].text
    assert all(r.source == "Client Rules" for r in records)
    assert len({r.id for r in records}) == len(records), "ids are distinct per section"


def test_fenced_code_blocks_are_stripped_before_chunking():
    """Mirrors `vault_sync._strip_fenced_blocks`, and for the same reason.

    A mermaid diagram inside a note is not prose a checker wants cited back at them, and leaving
    it in lets diagram syntax win keyword matches. That bug has been paid for once already.
    """
    note = (
        "# LAYERS\n"
        "All structural contours must rest on the approved border layer for production.\n"
        "```mermaid\n"
        "graph TD; TOLERANCE-->WELDING; ROUGHNESS-->TOLERANCE;\n"
        "```\n"
    )
    records = retrieval.chunk_markdown_by_heading(note, source="Rules")

    assert len(records) == 1
    assert "mermaid" not in records[0].text
    assert "graph TD" not in records[0].text
    assert "structural contours" in records[0].text


def test_heading_with_no_body_is_not_indexed():
    """A bare heading is noise in a ranking and dilutes idf."""
    note = "# EMPTY\n\n# REAL\nThis section has enough substance to be worth retrieving later.\n"
    records = retrieval.chunk_markdown_by_heading(note, source="Rules")

    assert [r.section for r in records] == ["REAL"]


def test_rule_notes_source_tolerates_a_missing_directory(tmp_path):
    """The client rules directory is gitignored, so absent is normal operation, not an error."""
    assert retrieval.records_from_rule_notes(tmp_path / "does-not-exist") == []


def test_standard_chunks_are_adapted_with_citation_metadata():
    class FakeChunk:
        def __init__(self, cid, content, header, standard_id, page):
            self.id, self.content, self.section_header = cid, content, header
            self.standard_id, self.chunk_index = standard_id, 0
            self.metadata = {"page_number": page, "standard_name": "JIS B 0405"}

    records = retrieval.records_from_standard_chunks(
        [
            FakeChunk("c1", "公差の一般規則 general tolerance rules", "TOLERANCES", "std-1", 12),
            FakeChunk("c2", "   ", "EMPTY", "std-1", 13),  # blank content is dropped
        ]
    )

    assert len(records) == 1
    assert records[0].id == "c1"
    assert records[0].citation() == "JIS B 0405 > TOLERANCES > p.12"
    assert records[0].metadata["standard_id"] == "std-1"
    assert records[0].text.startswith("TOLERANCES"), "header is prepended for topicality"


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

def test_index_survives_a_process_boundary(built_index):
    """Everything needed to search must be on disk — nothing may live only in memory."""
    store = retrieval.store_for(retrieval.STANDARDS, built_index)
    manifest = store.manifest()

    assert manifest is not None
    assert manifest.n_records == len(CORPUS)
    assert manifest.encoder_name == "tfidf-char_wb-2_4-v1"
    assert manifest.source_digest.startswith("sha256:")

    # A fresh store object, as a restarted process would have.
    reopened = retrieval.store_for(retrieval.STANDARDS, built_index)
    assert reopened.load(expected_encoder="tfidf-char_wb-2_4-v1") is retrieval.IndexStatus.OK
    assert len(reopened.records) == len(CORPUS)


def test_rebuilding_the_same_corpus_yields_the_same_digest(tmp_path):
    """So a genuine change can be told from a rebuild that changed nothing."""
    first = retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path / "a")
    second = retrieval.build_index(retrieval.STANDARDS, _records(), root=tmp_path / "b")

    assert first.built and second.built
    digest_a = retrieval.current_manifest(retrieval.STANDARDS, tmp_path / "a").source_digest
    digest_b = retrieval.current_manifest(retrieval.STANDARDS, tmp_path / "b").source_digest
    assert digest_a == digest_b


def test_empty_query_is_not_searched(built_index):
    outcome = retrieval.query("   ", root=built_index)
    assert outcome.hits == []
    assert outcome.status is retrieval.IndexStatus.OK
