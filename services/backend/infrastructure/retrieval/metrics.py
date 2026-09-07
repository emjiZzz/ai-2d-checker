"""Retrieval metrics — R2. `recall@k` and `MRR`, with counts and a chance baseline.

Why this stage exists at all. The standards pipeline shipped SHA-256 noise as an embedding
model and it survived for months, because *no number would have moved if it had been replaced by
a real one*. A retrieval system with no metric cannot tell a working encoder from a random one.
That is the whole argument, and it is why nothing tunes retrieval before this lands.

Counts beside every rate, on the pattern of `infrastructure/eval/scorer.py`. `0.83` means
nothing on its own; `0.83 (5/6)` tells you the sample is six queries and invites the right amount
of scepticism.

And a chance baseline beside every rate, which is this module's own addition and matters more
here than on the comparison track. `recall@k` is bounded below by what a *random* ranker achieves,
which is roughly `k/N` for a corpus of N documents. Over a 6-document corpus, `recall@5 = 0.83` is
exactly what shuffling would give you — a number that looks like success and measures nothing.
Reporting the floor alongside the value is what makes the difference visible. `informative` is
False when the measured value does not clear chance by a stated margin, and a report that is not
informative says so in its own output rather than in a comment somewhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

#: How far above the chance floor a result must sit before it is called informative. Not tuned —
#: chosen as "visibly better than shuffling" and stated so the reader can disagree with a number
#: rather than with a vibe.
INFORMATIVE_MARGIN = 0.15

#: Below this many labelled queries, no verdict is rendered at all. The staged plan asks for ~30;
#: this makes that a gate rather than an aspiration. The first run of this harness scored
#: `recall@5 = 1.00 (6/6)` and called itself informative on a lift of +0.17 over chance, directly
#: above a caveat explaining the labels were synthetic — a verdict line contradicting the caveat
#: beneath it is precisely how a meaningless number gets quoted on its own.
MIN_QUERIES_FOR_VERDICT = 30

#: The highest chance floor at which a verdict is still meaningful. If a shuffling ranker already
#: scores above this, `recall@k` has almost no room left to discriminate and the measured value is
#: mostly a restatement of the corpus size. 0.25 corresponds to roughly `N >= 4k` for a single
#: relevant document.
#:
#: The weaker gate this replaces was `corpus_size > k`, which passed a 6-document corpus at k=5:
#: a perfect ranker scored `recall@5 = 1.00` for a lift of +0.17 and was called informative, even
#: though it had retrieved 83% of the corpus. Retrieving five documents out of six is not
#: retrieval.
MAX_CHANCE_FLOOR = 0.25


@dataclass(frozen=True)
class LabelledQuery:
    """One hand-labelled `(query -> relevant chunks)` pair."""

    query_id: str
    query: str
    relevant_ids: frozenset[str]
    note: str = ""

    def __post_init__(self) -> None:
        if not self.relevant_ids:
            raise ValueError(
                f"Labelled query {self.query_id!r} names no relevant chunk. A query with no "
                "correct answer cannot contribute to recall — if the honest label is 'nothing in "
                "the corpus answers this', that is a coverage finding and belongs in the "
                "guideline's unanswerable list, not in the scored set."
            )


@dataclass(frozen=True)
class QueryOutcome:
    """What retrieval actually returned for one labelled query."""

    query_id: str
    retrieved_ids: tuple[str, ...]      # ranked, best first
    relevant_ids: frozenset[str]

    def first_relevant_rank(self) -> int | None:
        for rank, doc_id in enumerate(self.retrieved_ids, start=1):
            if doc_id in self.relevant_ids:
                return rank
        return None

    def hit_at(self, k: int) -> bool:
        return any(d in self.relevant_ids for d in self.retrieved_ids[:k])

    def n_relevant_at(self, k: int) -> int:
        return sum(1 for d in self.retrieved_ids[:k] if d in self.relevant_ids)


@dataclass(frozen=True)
class RetrievalScore:
    """The report. Every rate carries its counts and its chance floor."""

    k: int
    n_queries: int
    corpus_size: int

    recall_at_k: float
    recall_hits: int

    mrr: float
    reciprocal_ranks: tuple[float, ...] = field(repr=False, default=())

    precision_at_k: float = 0.0
    precision_numerator: int = 0
    precision_denominator: int = 0

    chance_recall_at_k: float = 0.0
    chance_mrr: float = 0.0

    #: True when any scored label was generated rather than judged by a person. Such a run can
    #: never be informative, no matter how good the numbers look — it measures whether the index
    #: can find text copied out of itself.
    synthetic_included: bool = False

    caveats: tuple[str, ...] = ()

    @property
    def recall_lift(self) -> float:
        """How far above a random ranker the measured recall sits."""
        return self.recall_at_k - self.chance_recall_at_k

    @property
    def informative(self) -> bool:
        """False when this run cannot support the conclusion someone will want to draw.

        Four independent gates, all of which must pass. Each exists because of a specific way a
        number here could be quoted misleadingly:

        - enough queries — the plan asks for ~30; below that a single query swings recall by
          more than the margin we are testing against.
        - a low enough chance floor — the corpus must be large enough relative to k that a
          shuffling ranker does not already score well. Retrieving 5 documents out of 6 is not
          retrieval, however good the resulting number looks.
        - lift over chance — `recall@5 = 1.00` on a 6-document corpus is a chance score of
          0.83 wearing a good disguise.
        - no synthetic labels — generated labels are circular by construction.
        """
        return (
            self.n_queries >= MIN_QUERIES_FOR_VERDICT
            and self.chance_recall_at_k <= MAX_CHANCE_FLOOR
            and self.recall_lift >= INFORMATIVE_MARGIN
            and not self.synthetic_included
        )

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "n_queries": self.n_queries,
            "corpus_size": self.corpus_size,
            "recall_at_k": round(self.recall_at_k, 4),
            "recall_hits": self.recall_hits,
            "mrr": round(self.mrr, 4),
            "precision_at_k": round(self.precision_at_k, 4),
            "precision_numerator": self.precision_numerator,
            "precision_denominator": self.precision_denominator,
            "chance_recall_at_k": round(self.chance_recall_at_k, 4),
            "chance_mrr": round(self.chance_mrr, 4),
            "recall_lift": round(self.recall_lift, 4),
            "informative": self.informative,
            "synthetic_included": self.synthetic_included,
            "caveats": list(self.caveats),
        }


def chance_recall_at_k(corpus_size: int, k: int, n_relevant: int = 1) -> float:
    """Expected `recall@k` from a ranker that shuffles.

    For one relevant document in a corpus of N, a random permutation puts it in the top k with
    probability k/N. With r relevant documents the chance of *at least one* landing in the top k
    is `1 - C(N-r, k)/C(N, k)`; the single-relevant case is the common one and reduces to k/N.
    """
    if corpus_size <= 0:
        return 0.0
    if k >= corpus_size:
        return 1.0

    numerator = 1.0
    for i in range(n_relevant):
        # Probability that all r relevant documents fall *outside* the top k.
        numerator *= (corpus_size - k - i) / (corpus_size - i)
        if numerator <= 0:
            return 1.0
    return 1.0 - numerator


def chance_mrr(corpus_size: int) -> float:
    """Expected MRR from a shuffling ranker with one relevant document: `H_N / N`."""
    if corpus_size <= 0:
        return 0.0
    harmonic = sum(1.0 / i for i in range(1, corpus_size + 1))
    return harmonic / corpus_size


def score_retrieval(
    outcomes: Sequence[QueryOutcome],
    k: int,
    corpus_size: int,
    synthetic_included: bool = False,
) -> RetrievalScore:
    """Aggregate per-query outcomes into a report.

    Raises nothing on a degenerate corpus — it scores what it can and attaches caveats, because a
    tool that refuses to run is a tool people stop running. The caveats are what stop the number
    being quoted out of context.
    """
    n = len(outcomes)
    caveats: list[str] = []

    if n == 0:
        return RetrievalScore(
            k=k,
            n_queries=0,
            corpus_size=corpus_size,
            recall_at_k=0.0,
            recall_hits=0,
            mrr=0.0,
            synthetic_included=synthetic_included,
            caveats=(
                "No labelled queries. There is no measurement here — this is the absence of one.",
            ),
        )

    hits = sum(1 for o in outcomes if o.hit_at(k))
    recall = hits / n

    reciprocal = tuple(
        (1.0 / rank) if (rank := o.first_relevant_rank()) is not None else 0.0
        for o in outcomes
    )
    mrr = sum(reciprocal) / n

    precision_num = sum(o.n_relevant_at(k) for o in outcomes)
    precision_den = sum(min(k, len(o.retrieved_ids)) for o in outcomes)
    precision = (precision_num / precision_den) if precision_den else 0.0

    mean_relevant = sum(len(o.relevant_ids) for o in outcomes) / n
    floor_recall = chance_recall_at_k(corpus_size, k, n_relevant=max(1, round(mean_relevant)))
    floor_mrr = chance_mrr(corpus_size)

    if floor_recall > MAX_CHANCE_FLOOR:
        caveats.append(
            f"The corpus holds {corpus_size} document(s) at k={k}, so a ranker returning "
            f"documents in random order already scores {floor_recall:.2f}. recall@{k} here is "
            f"arithmetic, not evidence — the corpus needs to be roughly {4 * k} documents or "
            f"more before this number discriminates."
        )
    if n < MIN_QUERIES_FOR_VERDICT:
        caveats.append(
            f"{n} labelled quer{'y' if n == 1 else 'ies'} against a {MIN_QUERIES_FOR_VERDICT} "
            f"minimum — no verdict is rendered below that. Every conclusion inherits this sample "
            f"size: a single query moves recall@{k} by {1.0 / n:.2f}, which is "
            f"{'more' if 1.0 / n > INFORMATIVE_MARGIN else 'less'} than the "
            f"{INFORMATIVE_MARGIN:.2f} lift margin itself."
        )
    if recall - floor_recall < INFORMATIVE_MARGIN and corpus_size > k:
        caveats.append(
            f"recall@{k} is {recall:.2f} against a chance floor of {floor_recall:.2f} — a lift of "
            f"{recall - floor_recall:+.2f}, below the {INFORMATIVE_MARGIN:.2f} margin. This does "
            f"not yet distinguish the encoder from shuffling."
        )

    return RetrievalScore(
        k=k,
        n_queries=n,
        corpus_size=corpus_size,
        recall_at_k=recall,
        recall_hits=hits,
        mrr=mrr,
        reciprocal_ranks=reciprocal,
        precision_at_k=precision,
        precision_numerator=precision_num,
        precision_denominator=precision_den,
        chance_recall_at_k=floor_recall,
        chance_mrr=floor_mrr,
        synthetic_included=synthetic_included,
        caveats=tuple(caveats),
    )


def format_report(score: RetrievalScore, collection: str, encoder: str) -> str:
    """Human-readable report. Counts and floors beside every rate, caveats in the output."""
    width = 78
    lines = [
        "-" * width,
        f"  RETRIEVAL EVAL - collection '{collection}', encoder '{encoder}'",
        "-" * width,
        f"  {score.n_queries} labelled quer(y/ies) over a {score.corpus_size}-document corpus",
        "",
        f"    recall@{score.k}      {score.recall_at_k:.2f} "
        f"({score.recall_hits}/{score.n_queries})"
        f"      chance {score.chance_recall_at_k:.2f}   lift {score.recall_lift:+.2f}",
        f"    MRR           {score.mrr:.2f}"
        f"                chance {score.chance_mrr:.2f}",
        f"    precision@{score.k}   {score.precision_at_k:.2f} "
        f"({score.precision_numerator}/{score.precision_denominator})",
        "",
    ]

    if score.informative:
        lines.append("  VERDICT: the measurement distinguishes this encoder from chance.")
    else:
        failed = []
        if score.synthetic_included:
            failed.append("labels are synthetic")
        if score.n_queries < MIN_QUERIES_FOR_VERDICT:
            failed.append(f"{score.n_queries} queries < {MIN_QUERIES_FOR_VERDICT}")
        if score.chance_recall_at_k > MAX_CHANCE_FLOOR:
            failed.append(
                f"corpus {score.corpus_size} too small for k {score.k} "
                f"(chance {score.chance_recall_at_k:.2f} > {MAX_CHANCE_FLOOR:.2f})"
            )
        if score.recall_lift < INFORMATIVE_MARGIN:
            failed.append(f"lift {score.recall_lift:+.2f} < {INFORMATIVE_MARGIN:.2f}")
        lines.append("  VERDICT: NOT INFORMATIVE - do not tune against this number.")
        lines.append(f"           failed gate(s): {'; '.join(failed)}")

    if score.caveats:
        lines.append("")
        for caveat in score.caveats:
            lines.append(f"  ! {caveat}")

    lines.append("-" * width)
    return "\n".join(lines)
