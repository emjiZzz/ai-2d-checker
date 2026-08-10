"""Lexical retrieval: char n-gram TF-IDF, plus BM25 over the same tokenisation.

**Why char n-grams and not words.** This is a Japanese CAD domain, and Japanese does not
word-segment on whitespace. A word-level tokeniser sees `素材調質施工` as one token and
`ユニットNo.` as one or two, so it can match neither a substring nor a near-miss. Character
n-grams degrade gracefully instead: `ユニットNo.` and `ユニット No` share most of their 2–4 grams.

It also mirrors `learning/finding_classifier.py`'s
`HashingVectorizer(analyzer="char_wb", ngram_range=(2, 4))` — the one learned component in this
system that demonstrably works. Reusing its shape means **one definition of "similar text"** across
retrieval and classification rather than two that drift.

**TF-IDF here, Hashing there, deliberately.** The classifier is stateless by design so its
vectoriser never enters the joblib bundle. Retrieval wants the opposite: a fitted vocabulary with
real idf weights, because idf is what stops `図` and `mm` — which appear in nearly every chunk —
from dominating a ranking. The cost is a fitted artifact to persist, which the store handles.

**Two rankers, and no blend by default.** TF-IDF cosine ranks by vector similarity; BM25 ranks by
saturating term frequency with length normalisation. They disagree usefully, and fusing them may
well beat either. **That is an R2 question, not an R1 one** — this stage has no retrieval metric
yet, so a fusion weight chosen here would be exactly the untested tuning the plan sequences R2
ahead of. `rrf` is implemented and tested; `tfidf` is the default until a number says otherwise.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from .encoder import EncoderError

Ranker = Literal["tfidf", "bm25", "rrf"]

# Matches finding_classifier.py. Do not drift these two apart without a reason written down.
ANALYZER = "char_wb"
NGRAM_RANGE = (2, 4)

# Caps the fitted vocabulary. Char 2-4 grams over a few thousand chunks of mixed Japanese and
# ASCII generate a very long tail of hapax n-grams that cost memory and contribute no ranking
# signal (an n-gram in one document has maximal idf and matches nothing else).
MAX_FEATURES = 2 ** 16

# BM25 constants, at the values the literature treats as defaults. Not tuned, and deliberately
# not swept here: with no retrieval metric there is nothing to sweep against. R2 owns that.
BM25_K1 = 1.5
BM25_B = 0.75

# Reciprocal-rank-fusion constant, at its conventional value. RRF needs no per-corpus weight,
# which is why it is the fusion offered — there is nothing to tune before there is a metric.
RRF_K = 60


class TfidfEncoder:
    """Char n-gram TF-IDF. The default encoder, and the only real one that exists."""

    name = "tfidf-char_wb-2_4-v1"

    _VECTORIZER_FILE = "encoder.joblib"

    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(
            analyzer=ANALYZER,
            ngram_range=NGRAM_RANGE,
            max_features=MAX_FEATURES,
            # L2 so a cosine is a plain dot product in the store, and long chunks do not
            # outrank short ones purely by having more mass.
            norm="l2",
            sublinear_tf=True,
            # Everything is lowercased for matching; Japanese is unaffected and ASCII layer
            # names like "BORDER"/"border" collapse, which is what a checker means by the same.
            lowercase=True,
        )
        self._fitted = False

    def fit(self, texts: Sequence[str]) -> TfidfEncoder:
        usable = [t for t in texts if t and t.strip()]
        if not usable:
            raise EncoderError(
                "Refusing to fit an encoder on zero non-empty texts. An index built from this "
                "would return nothing for every query, which is indistinguishable from "
                "'nothing relevant' — the exact failure mode R0 deleted. Check the source: "
                "either the collection is genuinely empty (do not build it) or the extraction "
                "step dropped everything."
            )
        self._vectorizer.fit(usable)
        self._fitted = True
        return self

    def encode(self, texts: Sequence[str]) -> csr_matrix:
        if not self._fitted:
            raise EncoderError(
                "TfidfEncoder.encode called before fit/load. It has no vocabulary and no idf, "
                "so it cannot encode anything. This raises rather than returning zeros because "
                "a zero vector ranks every document equally and looks like a working search."
            )
        return self._vectorizer.transform(list(texts))

    def save(self, directory: Path) -> None:
        if not self._fitted:
            raise EncoderError("Refusing to save an unfitted encoder.")
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._vectorizer, directory / self._VECTORIZER_FILE)

    def load(self, directory: Path) -> TfidfEncoder:
        path = directory / self._VECTORIZER_FILE
        if not path.exists():
            raise EncoderError(f"No fitted encoder at {path}.")
        self._vectorizer = joblib.load(path)
        self._fitted = True
        return self


def char_ngrams(text: str, ngram_range: tuple[int, int] = NGRAM_RANGE) -> list[str]:
    """Tokenise the way `char_wb` does, for BM25.

    `char_wb` pads each whitespace-delimited word with a space either side and slides an n-gram
    window inside that padding, so n-grams never span a word boundary. Reproduced here rather
    than reused because sklearn exposes it only through a fitted vectoriser, and BM25 needs the
    token stream itself rather than a matrix.
    """
    low, high = ngram_range
    tokens: list[str] = []
    for word in text.lower().split():
        padded = f" {word} "
        for n in range(low, high + 1):
            if len(padded) < n:
                continue
            tokens.extend(padded[i : i + n] for i in range(len(padded) - n + 1))
    return tokens


class BM25:
    """Okapi BM25 over char n-grams.

    Kept independent of the TF-IDF encoder rather than sharing its matrix: BM25 needs raw term
    frequencies and document lengths, and the encoder's matrix is normalised and idf-weighted,
    so deriving one from the other would silently apply two weighting schemes.
    """

    def __init__(self, k1: float = BM25_K1, b: float = BM25_B) -> None:
        self.k1 = k1
        self.b = b
        self._doc_freqs: list[Counter[str]] = []
        self._doc_lens: np.ndarray = np.zeros(0)
        self._avg_len: float = 0.0
        self._idf: dict[str, float] = {}
        self._n_docs = 0

    def fit(self, texts: Sequence[str]) -> BM25:
        self._doc_freqs = [Counter(char_ngrams(t)) for t in texts]
        self._doc_lens = np.array([sum(c.values()) for c in self._doc_freqs], dtype=np.float64)
        self._n_docs = len(texts)
        self._avg_len = float(self._doc_lens.mean()) if self._n_docs else 0.0

        containing: Counter[str] = Counter()
        for freqs in self._doc_freqs:
            containing.update(freqs.keys())
        # Robertson/Sparck-Jones idf with the +1 smoothing that keeps it non-negative, so a
        # term present in every document contributes ~0 rather than a negative score.
        self._idf = {
            term: math.log(1.0 + (self._n_docs - n + 0.5) / (n + 0.5))
            for term, n in containing.items()
        }
        return self

    def scores(self, query: str) -> np.ndarray:
        if self._n_docs == 0:
            return np.zeros(0)
        out = np.zeros(self._n_docs, dtype=np.float64)
        query_terms = Counter(char_ngrams(query))
        for term in query_terms:
            idf = self._idf.get(term)
            if idf is None:
                continue
            for doc_i, freqs in enumerate(self._doc_freqs):
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (
                    1.0 - self.b + self.b * self._doc_lens[doc_i] / (self._avg_len or 1.0)
                )
                out[doc_i] += idf * (tf * (self.k1 + 1.0)) / denom
        return out


def reciprocal_rank_fusion(*rankings: Sequence[int], k: int = RRF_K) -> list[tuple[int, float]]:
    """Fuse ranked index lists into one, by 1/(k + rank).

    Parameter-free apart from `k`, which is why it is the fusion offered: there is no per-corpus
    weight to fit, so using it does not smuggle in tuning ahead of R2's metric.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
