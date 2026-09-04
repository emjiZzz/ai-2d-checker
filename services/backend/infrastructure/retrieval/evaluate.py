"""Runs a label set against a live index and produces a `RetrievalScore` — R2.

Two things this does that a naive harness would not:

It reports the corpus census before the metric. A retrieval number is uninterpretable without
knowing how many documents were searched, and on this system that turns out to be the entire
finding rather than a footnote. An empty collection is a *census* result, not a recall of 0.00.

It refuses to score labels authored against a different corpus. See `labels.py` — a stale
label scores as a miss, so corpus drift presents as "the encoder regressed", which is the shape
most likely to send someone off tuning the wrong thing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import query as run_query
from .index_builder import (
    CORRECTIONS,
    DOMAIN_RULES,
    ENTITIES,
    FINDINGS,
    LESSONS,
    STANDARDS,
    VAULT,
    store_for,
)
from .labels import LabelSet
from .metrics import QueryOutcome, RetrievalScore, score_retrieval
from .store import IndexStatus

ALL_COLLECTIONS = (STANDARDS, DOMAIN_RULES, LESSONS, CORRECTIONS, FINDINGS, VAULT, ENTITIES)


@dataclass(frozen=True)
class CollectionCensus:
    collection: str
    status: IndexStatus
    n_records: int
    encoder: str
    source_digest: str

    @property
    def usable(self) -> bool:
        return self.status is IndexStatus.OK and self.n_records > 0


def census(collection: str, root: Path | None = None) -> CollectionCensus:
    """What is actually in this collection. Answered without running a query."""
    store = store_for(collection, root)
    status = store.load()
    manifest = store.manifest()
    return CollectionCensus(
        collection=collection,
        status=status,
        n_records=manifest.n_records if manifest else 0,
        encoder=manifest.encoder_name if manifest else "",
        source_digest=manifest.source_digest if manifest else "",
    )


def census_all(root: Path | None = None) -> list[CollectionCensus]:
    return [census(name, root) for name in ALL_COLLECTIONS]


@dataclass(frozen=True)
class EvaluationResult:
    collection: str
    census: CollectionCensus
    score: RetrievalScore
    k: int
    include_synthetic: bool

    def to_dict(self) -> dict:
        return {
            "collection": self.collection,
            "corpus": {
                "status": str(self.census.status),
                "n_records": self.census.n_records,
                "encoder": self.census.encoder,
                "source_digest": self.census.source_digest,
            },
            "include_synthetic": self.include_synthetic,
            **self.score.to_dict(),
        }


def evaluate(  # noqa: PLR0913 — each argument is a distinct evaluation axis; see below
    label_set: LabelSet,
    collection: str,
    k: int = 5,
    include_synthetic: bool = False,
    root: Path | None = None,
    check_drift: bool = True,
) -> EvaluationResult:
    """Score `label_set` against the live index for `collection`.

    The argument list is wide because each entry is an independent axis a caller legitimately
    varies — `k` for the cutoff, `include_synthetic` for smoke runs, `root` for test isolation,
    `check_drift` to score a knowingly-stale set. Collapsing them into a config object would hide
    `include_synthetic` in particular, and that flag needs to stay visible at every call site:
    it is the difference between a measurement and a smoke test.
    """
    corpus = census(collection, root)

    if check_drift and corpus.usable:
        label_set.assert_matches_index(corpus.source_digest)

    queries = label_set.scored(include_synthetic=include_synthetic)
    outcomes: list[QueryOutcome] = []

    for labelled in queries:
        outcome = run_query(labelled.query, collection=collection, top_k=k, root=root)
        outcomes.append(
            QueryOutcome(
                query_id=labelled.query_id,
                retrieved_ids=tuple(hit.record.id for hit in outcome.hits),
                relevant_ids=labelled.relevant_ids,
            )
        )

    synthetic_scored = include_synthetic and len(queries) > len(label_set.human_labels())
    score = score_retrieval(
        outcomes,
        k=k,
        corpus_size=corpus.n_records,
        synthetic_included=synthetic_scored,
    )

    # Fold the census into the caveats, so a report read in isolation still carries the reason.
    extra: list[str] = list(score.caveats)
    if not corpus.usable:
        extra.insert(
            0,
            f"Collection '{collection}' is {corpus.status} with {corpus.n_records} record(s). "
            f"There is nothing to retrieve from, so no number below is a measurement of "
            f"retrieval quality.",
        )
    if include_synthetic:
        extra.insert(
            0,
            "Synthetic labels are included. These are generated from the corpus, so they measure "
            "whether the index can find text copied out of it — a smoke test, not evidence. "
            "This run must not be published as a baseline.",
        )

    return EvaluationResult(
        collection=collection,
        census=corpus,
        score=RetrievalScore(
            k=score.k,
            n_queries=score.n_queries,
            corpus_size=score.corpus_size,
            recall_at_k=score.recall_at_k,
            recall_hits=score.recall_hits,
            mrr=score.mrr,
            reciprocal_ranks=score.reciprocal_ranks,
            precision_at_k=score.precision_at_k,
            precision_numerator=score.precision_numerator,
            precision_denominator=score.precision_denominator,
            chance_recall_at_k=score.chance_recall_at_k,
            chance_mrr=score.chance_mrr,
            synthetic_included=score.synthetic_included,
            caveats=tuple(extra),
        ),
        k=k,
        include_synthetic=include_synthetic,
    )


def format_census(entries: list[CollectionCensus]) -> str:
    width = 78
    lines = ["-" * width, "  CORPUS CENSUS", "-" * width]
    for entry in entries:
        marker = "ok " if entry.usable else "!! "
        lines.append(
            f"  {marker}{entry.collection:<14s} {str(entry.status):<8s} "
            f"{entry.n_records:>6d} record(s)  {entry.encoder or '-'}"
        )
    if not any(e.usable for e in entries):
        lines += [
            "",
            "  Every collection is empty or unbuilt. Retrieval cannot be measured, and more",
            "  importantly it is not doing anything for a user today. That is a data finding,",
            "  not an encoder finding — do not respond to it by changing the encoder.",
        ]
    lines.append("-" * width)
    return "\n".join(lines)
