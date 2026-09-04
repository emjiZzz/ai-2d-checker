"""The encoder seam -- what turns text into something searchable.

One implementation today (`lexical.TfidfEncoder`), and the interface exists anyway for the reason
in ADR-008: dense embeddings must win a measurement before they ship. Without a seam, "try a real
embedding model" is a rewrite and never gets tested; with one it is a subclass and an A/B on R2.

It is also what R0 cleaned up after. The deleted stack had no interface, so the fake embedding
model was imported directly by four modules with no single place to swap it or inspect it. An
encoder must be able to say what it is (`name`), and the manifest beside every index records that
name, so an index built by one encoder cannot be silently searched by another.

No encoder here may fabricate a vector; if it cannot encode, it raises. The predecessor returned
`np.random.default_rng(sha256(text))` and nothing downstream could tell.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from scipy.sparse import csr_matrix


class EncoderError(RuntimeError):
    """An encoder could not produce vectors. Never substitute a placeholder for this."""


@runtime_checkable
class Encoder(Protocol):
    """Turns text into L2-normalised vectors that a cosine brute force can rank.

    Sparse by contract. Char n-gram spaces are wide and mostly empty, and a dense array of them
    is the wrong container — see `store.py`. A dense encoder, should one ever earn its place,
    returns a one-row-per-text `csr_matrix` too; the density is its business, not the store's.
    """

    #: Stable identifier written into every index manifest. Changing what an encoder does
    #: without changing its name will silently mix incompatible vectors — bump it.
    name: str

    def fit(self, texts: Sequence[str]) -> Encoder:
        """Learn whatever state the encoder needs (vocabulary, idf). Returns self."""
        ...

    def encode(self, texts: Sequence[str]) -> csr_matrix:
        """Encode texts into an L2-normalised `(len(texts), dim)` sparse matrix."""
        ...

    def save(self, directory: Path) -> None:
        """Persist fitted state into `directory`."""
        ...

    def load(self, directory: Path) -> Encoder:
        """Restore fitted state from `directory`. Returns self."""
        ...
