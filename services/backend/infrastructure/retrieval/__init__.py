"""Local lexical retrieval — R1 of the standards knowledge plan.

The public surface is `query()`. Everything else is an implementation detail of how a chunk gets
ranked, and is importable for tests and for the R2 metric harness.

```python
from services.backend.infrastructure import retrieval

outcome = retrieval.query("公差 tolerance", collection=retrieval.STANDARDS, top_k=5)
if not outcome.answered:
    ...                                   # the index is missing/empty/stale — say so
for hit in outcome.hits:
    print(hit.rank, round(hit.score, 3), hit.record.citation())
```

**What this is.** Exact char n-gram TF-IDF cosine over a local sparse index. Offline, no model
download, no network, no LLM. Retrieval *only* — it hands cited chunks to a human and generates
nothing, so there is no hallucination surface ([[ADR-008]]).

**What this is not.** It is not semantic. It cannot match a synonym, a paraphrase, or an English
term against its Japanese equivalent unless they share characters. Saying so plainly is the point:
the stack this replaces claimed "semantic vector similarity" and computed
`np.random.default_rng(sha256(text))`.

**Empty is not the same as nothing relevant.** `query()` returns a `SearchOutcome` whose `status`
distinguishes *"the index answered and nothing matched"* from *"there is no index"*. The staged
plan names that conflation as R1's chief risk, and it is the same shape as the R0 defect: a read
path returning `[]` hid a write path that had never written a record.
"""

from __future__ import annotations

import time

from ...logger import logger
from .encoder import Encoder, EncoderError
from .index_builder import (
    DOMAIN_RULES,
    LESSONS,
    STANDARDS,
    BuildResult,
    build_index,
    chunk_markdown_by_heading,
    current_manifest,
    index_root,
    records_from_rule_notes,
    records_from_standard_chunks,
    store_for,
)
from .lexical import BM25, TfidfEncoder, char_ngrams, reciprocal_rank_fusion
from .store import Hit, IndexStatus, Manifest, Record, SearchOutcome, VectorStore

__all__ = [
    "query",
    "STANDARDS",
    "DOMAIN_RULES",
    "LESSONS",
    "SearchOutcome",
    "IndexStatus",
    "Hit",
    "Record",
    "Manifest",
    "VectorStore",
    "Encoder",
    "EncoderError",
    "TfidfEncoder",
    "BM25",
    "char_ngrams",
    "reciprocal_rank_fusion",
    "build_index",
    "BuildResult",
    "records_from_standard_chunks",
    "records_from_rule_notes",
    "chunk_markdown_by_heading",
    "current_manifest",
    "index_root",
    "store_for",
]

#: Queries slower than this are logged. The exit criterion for R1 is <100 ms; exceeding it does
#: not fail the query, it reports that the assumption behind brute force stopped holding.
SLOW_QUERY_MS = 100.0


def query(
    text: str,
    collection: str = STANDARDS,
    top_k: int = 5,
    min_score: float = 0.0,
    root=None,
) -> SearchOutcome:
    """Rank `collection` against `text`. Offline, exact, and honest about an unusable index.

    `min_score` defaults to 0.0, which drops only the genuinely orthogonal. It is not a relevance
    threshold — no threshold can be justified before R2 produces a retrieval metric, and picking
    one here would be the untested tuning that stage exists to prevent.
    """
    if not text or not text.strip():
        return SearchOutcome(
            hits=[],
            status=IndexStatus.OK,
            collection=collection,
            detail="Empty query; nothing was searched.",
        )

    store = store_for(collection, root)
    encoder = TfidfEncoder()
    try:
        encoder.load(store.directory)
    except EncoderError as err:
        detail = (
            f"No usable encoder for collection '{collection}': {err} The index has not been "
            f"built, so this is not a 'no results' answer."
        )
        logger.warning(f"[retrieval] {detail}")
        return SearchOutcome(
            hits=[], status=IndexStatus.MISSING, collection=collection, detail=detail
        )

    started = time.perf_counter()
    outcome = store.search(
        query_vector=encoder.encode([text]),
        top_k=top_k,
        min_score=min_score,
        expected_encoder=encoder.name,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if elapsed_ms > SLOW_QUERY_MS:
        logger.warning(
            f"[retrieval] Query over '{collection}' took {elapsed_ms:.1f} ms, above the "
            f"{SLOW_QUERY_MS:.0f} ms brute-force budget. Exact search is linear in corpus size; "
            f"if the corpus has grown substantially this is the signal to revisit that choice."
        )
    return outcome
