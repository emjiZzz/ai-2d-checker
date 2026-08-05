"""Offline evaluation substrate — Stage 0 of the AI maturity ladder.

Nothing in this package may import Beanie, Mongo, or the Gemini client. The whole point
is that `generate_deterministic_candidates` can be driven from disk, in-process, with no
network and no database, so a number can be produced at all. See
`docs/vault/01 - Architecture/AI Maturity Ladder — Staged Plan.md` (Stage 0b) and
`docs/vault/00 - AI Maturity Status.md`.

Layout:
  * `serialize` — duck-typed stand-ins for `DrawingDocument` / `ExtractedEntity`, and the
    canonical on-disk payload format they round-trip through.
  * `corpus` — the manifest, the labels, sha256 drift detection, and held-out discipline.
"""

from .corpus import (
    CorpusDriftError,
    CorpusPair,
    EvalCorpus,
    ExpectedFinding,
    HeldOutAccessError,
    LabelSchemaError,
    load_corpus,
)
from .serialize import EvalDrawing, EvalEntity

__all__ = [
    "CorpusDriftError",
    "CorpusPair",
    "EvalCorpus",
    "EvalDrawing",
    "EvalEntity",
    "ExpectedFinding",
    "HeldOutAccessError",
    "LabelSchemaError",
    "load_corpus",
]
