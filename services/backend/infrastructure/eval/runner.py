"""Run the comparison engine over the corpus, offline — Stage 0e.

Calls `generate_deterministic_candidates` **directly**: not `perform_drawing_comparison`,
which is the Mongo-and-cache wrapper, and never the comparison cache. A cached audit is
served in ~0.14 s and would silently answer with whatever the engine did last time, which
is precisely how a measurement becomes a measurement of nothing.

The offline guarantee is asserted, not assumed. `no_network()` patches `socket.connect` to
raise on any non-local address for the duration of a run, so "zero network calls" is a
property the runner enforces rather than a claim in a document.
"""

from __future__ import annotations

import contextlib
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .corpus import CorpusPair, EvalCorpus
from .scorer import CorpusScore, Prediction, score_pair

# Only the deterministic method can run offline today. `rag_ai`, `hybrid` and `ai_vision`
# all call Gemini, and there is no recorded output in this repository to replay — that is
# Stage 0f's record/replay cassette. Refusing loudly beats emitting a number that quietly
# cost money and cannot be reproduced.
OFFLINE_METHODS = frozenset({"rag", "deterministic"})

_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", ""})


class NetworkCallDuringEval(AssertionError):
    """An eval run tried to reach the network. The number it would produce is not offline."""


@contextlib.contextmanager
def no_network() -> Iterator[None]:
    """Fail loudly on any non-local socket for the duration of the block.

    Local connections stay open on purpose: Mongo may be running on the dev machine, and
    the point of this guard is that no *paid, non-reproducible* call happens — not that
    the process is hermetic.
    """
    original = socket.socket.connect

    def guarded(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host) not in _LOCAL_HOSTS:
            raise NetworkCallDuringEval(
                f"The eval run attempted a network call to {address!r}. Title-block OCR "
                f"fires on a cache miss — check `tools/eval_corpus.py verify` for pairs "
                f"missing their OCR cache entry."
            )
        return original(self, address, *args, **kwargs)

    socket.socket.connect = guarded  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = original  # type: ignore[method-assign]


@dataclass
class RunResult:
    score: CorpusScore
    seconds: float
    pairs_run: int
    skipped: list[str]
    ocr_restored: list[str] = field(default_factory=list)


async def run_pair(pair: CorpusPair, method: str = "rag") -> tuple[list[Prediction], list[Any]]:
    """One pair through the engine. Returns (predictions, raw candidates)."""
    if method not in OFFLINE_METHODS:
        raise ValueError(
            f"method {method!r} calls Gemini and cannot be evaluated offline. Stage 0f's "
            f"cassette is what unlocks it; until then only {sorted(OFFLINE_METHODS)} run here."
        )
    from ..audit.comparison.orchestrator import generate_deterministic_candidates

    ref_drawing, rev_drawing, ref_entities, rev_entities = pair.load()
    candidates, _rollups, _warnings = await generate_deterministic_candidates(
        ref_drawing, rev_drawing, ref_entities, rev_entities
    )
    # A prediction is a reported discrepancy. MATCHED rows are checklist entries for items
    # checked and found unchanged — counting them would put precision near zero on a
    # perfect run. See scorer.py.
    predictions = [
        Prediction.from_candidate(c)
        for c in candidates
        if str(getattr(c, "status", "")) != "MATCHED"
    ]
    return predictions, candidates


async def run_corpus(
    corpus: EvalCorpus,
    *,
    method: str = "rag",
    provenance: str | None = None,
    enforce_offline: bool = True,
    progress: Any = None,
) -> RunResult:
    """Score every labelled pair in the corpus."""
    score = CorpusScore()
    skipped: list[str] = []
    started = time.time()

    # Put every captured title-block reading back before the guard goes up. The engine reads
    # the OCR cache internally with no seam to pass a reading through, and a missing entry
    # does not fail — it silently falls back to spatial title extraction on that side only,
    # which is how a deleted cache changed the meaning of a score without changing a byte of
    # the corpus. Restoring first makes the score a function of the corpus alone.
    restored: list[str] = []
    for pair in corpus.pairs:
        restored.extend(pair.restore_ocr_cache())
    guard = no_network() if enforce_offline else contextlib.nullcontext()
    with guard:
        for pair in corpus.pairs:
            if provenance and pair.provenance != provenance:
                continue
            if pair.labels is None:
                # Unlabelled pairs have no ground truth. Skipped and reported rather than
                # scored as zero findings, which would read as a perfect result.
                skipped.append(f"{pair.pair_id} (unlabelled)")
                continue
            ref_drawing, rev_drawing, ref_entities, rev_entities = pair.load()
            predictions, _ = await run_pair(pair, method=method)
            score.pair_scores.append(
                score_pair(pair, predictions, ref_entities, rev_entities)
            )
            if progress:
                progress(pair.pair_id)

    return RunResult(
        score=score,
        seconds=time.time() - started,
        pairs_run=len(score.pair_scores),
        skipped=skipped,
        ocr_restored=restored,
    )
