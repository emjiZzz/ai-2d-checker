"""R2 — the retrieval metric, and the gates that stop it being quoted out of context.

The arithmetic here is standard and would be dull to over-test. What is worth pinning is the
refusal logic, because that is the part R2 exists for. The stage's whole argument is that
SHA-256 embeddings survived in production for months because no number would have moved if they
were replaced by a real model; a metric that reports a confident figure over six documents
reproduces that failure with extra steps.

So most of this file is about a report declining to be evidence. The first run of this harness
scored `recall@5 = 1.00 (6/6)` and called itself informative — directly above a caveat saying the
labels were synthetic. `test_a_perfect_score_on_synthetic_labels_is_not_informative` is that bug.
"""
from __future__ import annotations

import json

import pytest

from services.backend.infrastructure.retrieval.labels import (
    GUIDELINE_VERSION,
    LABEL_SCHEMA_VERSION,
    LabelDriftError,
    LabelError,
    LabelSet,
    Provenance,
    RetrievalLabel,
)
from services.backend.infrastructure.retrieval.metrics import (
    INFORMATIVE_MARGIN,
    MIN_QUERIES_FOR_VERDICT,
    LabelledQuery,
    QueryOutcome,
    chance_mrr,
    chance_recall_at_k,
    format_report,
    score_retrieval,
)

#: Sample size used by most tests here: comfortably above MIN_QUERIES_FOR_VERDICT, so a test
#: that expects a verdict is not silently gated by sample size instead of by what it targets.
N_QUERIES = 40


def _outcomes(n: int, retrieved_rank_of_relevant: int | None = 1, corpus_prefix: str = "d"):
    """n queries, each with one relevant doc placed at the given rank (None = absent)."""
    out = []
    for i in range(n):
        relevant = f"{corpus_prefix}{i}-relevant"
        ranked = [f"{corpus_prefix}{i}-filler{j}" for j in range(10)]
        if retrieved_rank_of_relevant is not None:
            ranked.insert(retrieved_rank_of_relevant - 1, relevant)
        out.append(
            QueryOutcome(
                query_id=f"q{i}",
                retrieved_ids=tuple(ranked[:10]),
                relevant_ids=frozenset({relevant}),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------

def test_recall_and_mrr_on_a_perfect_ranker():
    score = score_retrieval(_outcomes(N_QUERIES, 1), k=5, corpus_size=500)

    assert score.recall_at_k == 1.0
    assert score.recall_hits == N_QUERIES
    assert score.mrr == 1.0


def test_recall_counts_a_hit_anywhere_in_the_top_k_but_mrr_discounts_it():
    """recall@k is a hit/miss; MRR is where ranking quality actually shows."""
    score = score_retrieval(_outcomes(N_QUERIES, 4), k=5, corpus_size=500)

    assert score.recall_at_k == 1.0, "rank 4 is inside the top 5"
    assert score.mrr == pytest.approx(0.25), "but it is the 4th result, so 1/4"


def test_a_relevant_document_outside_k_is_a_miss():
    score = score_retrieval(_outcomes(N_QUERIES, 9), k=5, corpus_size=500)

    assert score.recall_at_k == 0.0
    assert score.recall_hits == 0
    assert score.mrr == pytest.approx(1 / 9), "MRR still sees it; recall@5 does not"


def test_a_relevant_document_never_retrieved_scores_zero():
    score = score_retrieval(_outcomes(N_QUERIES, None), k=5, corpus_size=500)

    assert score.recall_at_k == 0.0
    assert score.mrr == 0.0


def test_counts_accompany_every_rate():
    """The house style from `eval/scorer.py`: a bare rate invites the wrong confidence."""
    score = score_retrieval(_outcomes(N_QUERIES, 1), k=5, corpus_size=500)
    payload = score.to_dict()

    assert payload["recall_hits"] == N_QUERIES and payload["n_queries"] == N_QUERIES
    assert payload["precision_numerator"] == N_QUERIES
    assert payload["precision_denominator"] == N_QUERIES * 5, "one denominator slot per k"
    assert payload["precision_at_k"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# The chance floor — R2's central idea
# ---------------------------------------------------------------------------

def test_chance_recall_is_k_over_n_for_a_single_relevant_document():
    assert chance_recall_at_k(100, 5) == pytest.approx(0.05)
    assert chance_recall_at_k(6, 5) == pytest.approx(5 / 6, abs=1e-9)
    assert chance_recall_at_k(5, 5) == 1.0, "k >= N means everything is retrieved"
    assert chance_recall_at_k(0, 5) == 0.0


def test_chance_recall_rises_with_more_relevant_documents():
    """With several right answers, a shuffler is likelier to land one in the top k."""
    assert chance_recall_at_k(100, 5, n_relevant=3) > chance_recall_at_k(100, 5, n_relevant=1)


def test_chance_mrr_is_the_harmonic_mean_position():
    assert chance_mrr(6) == pytest.approx(sum(1 / i for i in range(1, 7)) / 6)
    assert chance_mrr(1) == 1.0, "one document is always rank 1"


def test_lift_is_what_makes_a_recall_number_readable():
    """`recall@5 = 1.00` is a triumph over 500 documents and a tautology over 6."""
    big = score_retrieval(_outcomes(N_QUERIES, 1), k=5, corpus_size=500)
    tiny = score_retrieval(_outcomes(N_QUERIES, 1), k=5, corpus_size=6)

    assert big.recall_at_k == tiny.recall_at_k == 1.0, "identical headline number"
    assert big.recall_lift == pytest.approx(0.99, abs=0.01)
    assert tiny.recall_lift == pytest.approx(0.17, abs=0.01)
    assert big.informative and not tiny.informative


# ---------------------------------------------------------------------------
# Refusal — the part that matters
# ---------------------------------------------------------------------------

def test_a_perfect_score_on_synthetic_labels_is_not_informative():
    """The bug this harness shipped with, on its first run, pinned.

    `recall@5 = 1.00 (6/6)` printed `VERDICT: the measurement distinguishes this encoder from
    chance` immediately above a caveat explaining the labels were generated from the corpus.
    """
    score = score_retrieval(
        _outcomes(N_QUERIES, 1), k=5, corpus_size=500, synthetic_included=True
    )

    assert score.recall_at_k == 1.0
    assert not score.informative, "generated labels are circular; the score cannot be evidence"
    assert "labels are synthetic" in format_report(score, "c", "e")


def test_too_few_queries_renders_no_verdict_however_good_the_number():
    score = score_retrieval(_outcomes(MIN_QUERIES_FOR_VERDICT - 1, 1), k=5, corpus_size=500)

    assert score.recall_at_k == 1.0
    assert not score.informative
    assert f"< {MIN_QUERIES_FOR_VERDICT}" in format_report(score, "c", "e")


def test_a_corpus_too_small_for_k_is_never_informative():
    """The gate is the chance floor, not `N > k`.

    `N = 6, k = 5` passes a naive `N > k` check while a shuffler already scores 0.83 — that was
    the original gate, and a perfect ranker cleared it on a +0.17 lift.
    """
    for corpus_size in (5, 6, 10):
        score = score_retrieval(_outcomes(N_QUERIES, 1), k=5, corpus_size=corpus_size)
        assert not score.informative, f"corpus of {corpus_size} at k=5 cannot discriminate"
        assert any("arithmetic, not evidence" in c for c in score.caveats)

    roomy = score_retrieval(_outcomes(N_QUERIES, 1), k=5, corpus_size=100)
    assert roomy.informative, "a corpus 20x k leaves the metric room to discriminate"


def test_an_empty_label_set_reports_the_absence_of_a_measurement():
    score = score_retrieval([], k=5, corpus_size=500)

    assert score.n_queries == 0
    assert not score.informative
    assert any("absence of one" in c for c in score.caveats)


def test_a_result_barely_above_chance_says_so():
    """40 queries, corpus of 8, k=5 -> chance 0.625. A 1.00 recall is only +0.375... informative.
    But place the relevant doc outside k for most queries and the lift collapses."""
    outcomes = _outcomes(10, 1) + _outcomes(30, 9, corpus_prefix="e")
    score = score_retrieval(outcomes, k=5, corpus_size=8)

    assert score.recall_at_k == pytest.approx(0.25)
    assert score.recall_lift < INFORMATIVE_MARGIN
    assert not score.informative
    assert any("does not yet distinguish the encoder from shuffling" in c for c in score.caveats)


def test_the_report_names_every_failed_gate():
    score = score_retrieval(_outcomes(3, 9), k=5, corpus_size=4, synthetic_included=True)
    report = format_report(score, "domain_rules", "tfidf")

    assert "NOT INFORMATIVE" in report
    for expected in ("labels are synthetic", "3 queries < 30", "corpus 4 too small for k 5"):
        assert expected in report, f"missing gate: {expected}"


# ---------------------------------------------------------------------------
# Label discipline
# ---------------------------------------------------------------------------

def test_a_label_with_no_relevant_chunk_is_rejected():
    with pytest.raises(ValueError, match="names no relevant chunk"):
        LabelledQuery(query_id="q1", query="tolerance", relevant_ids=frozenset())


def test_provenance_is_required_and_validated():
    with pytest.raises(LabelError, match="provenance"):
        RetrievalLabel.from_dict(
            {"query_id": "q1", "query": "t", "relevant_ids": ["a"], "provenance": "guessed"}
        )


def test_synthetic_labels_are_excluded_from_scoring_by_default():
    label_set = LabelSet(
        collection="standards",
        guideline_version=GUIDELINE_VERSION,
        source_digest="sha256:abc",
        labels=[
            RetrievalLabel("h1", "real query", ["c1"], Provenance.HUMAN),
            RetrievalLabel("s1", "generated", ["c2"], Provenance.SYNTHETIC),
        ],
    )

    assert [q.query_id for q in label_set.scored()] == ["h1"]
    assert len(label_set.scored(include_synthetic=True)) == len(label_set.labels)
    assert len(label_set.human_labels()) == 1


def test_labels_from_a_different_guideline_are_refused(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": LABEL_SCHEMA_VERSION,
                "collection": "standards",
                "guideline_version": "2020-01-01",
                "source_digest": "",
                "labels": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LabelError, match="authored under guideline"):
        LabelSet.load(path)


def test_labels_authored_against_a_different_corpus_are_refused():
    """Stale labels score as misses, so drift looks like the encoder regressing."""
    label_set = LabelSet(
        collection="standards",
        guideline_version=GUIDELINE_VERSION,
        source_digest="sha256:original",
    )

    label_set.assert_matches_index("sha256:original")  # matching digest is fine

    with pytest.raises(LabelDriftError, match="looks exactly"):
        label_set.assert_matches_index("sha256:rebuilt-differently")


def test_a_label_set_round_trips(tmp_path):
    original = LabelSet(
        collection="standards",
        guideline_version=GUIDELINE_VERSION,
        source_digest="sha256:abc",
        labels=[RetrievalLabel("q1", "公差 tolerance", ["c1", "c2"], Provenance.HUMAN, "note")],
        unanswerable=["a question the corpus cannot answer"],
    )
    path = tmp_path / "labels.json"
    original.save(path)

    reloaded = LabelSet.load(path)
    assert reloaded.labels[0].query == "公差 tolerance"
    assert reloaded.labels[0].relevant_ids == ["c1", "c2"]
    assert reloaded.labels[0].provenance is Provenance.HUMAN
    assert reloaded.unanswerable == ["a question the corpus cannot answer"]
