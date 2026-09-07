"""The learned classifier itself.

Generic multiclass classifier over finding feature dicts, used for both the verdict head
(labels 0/1 — is this a true discrepancy?) and the category head (labels = category strings).

Design: char n-gram text goes through a STATELESS HashingVectorizer (no vocabulary to fit or
persist), the categorical/numeric features through a fitted DictVectorizer, and the two sparse
blocks are concatenated into a LogisticRegression head. LogisticRegression is chosen over the
gradient-boosted tree the plan sketched because the feature space is high-dimensional and
SPARSE (char n-grams) — HistGradientBoosting requires dense input and does not scale to a
2**14 hashed text space, whereas LogisticRegression handles sparse input natively, trains in
milliseconds on a few hundred examples, gives usable predict_proba, and supports
class_weight='balanced' for the label imbalance this problem starts with.
"""
from __future__ import annotations

from typing import Optional

from scipy.sparse import hstack
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import LogisticRegression

from .feature_extractor import CAT_NUM_KEYS

# Stateless: recreated on import in any process, so it never needs to be pickled. Kept
# module-level (not an instance attribute) so it stays out of the joblib bundle.
_HASHER = HashingVectorizer(
    analyzer="char_wb",
    ngram_range=(2, 4),
    n_features=2 ** 14,
    alternate_sign=False,
    norm="l2",
)


class FindingClassifier:
    def __init__(self) -> None:
        self._dv = DictVectorizer(sparse=True)
        self._clf = LogisticRegression(max_iter=2000, class_weight="balanced")
        self.classes_: list = []
        self.n_samples: int = 0

    @staticmethod
    def _texts(rows: list[dict]) -> list[str]:
        return [r.get("text_combined", "") for r in rows]

    @staticmethod
    def _cats(rows: list[dict]) -> list[dict]:
        return [{k: r[k] for k in CAT_NUM_KEYS if k in r} for r in rows]

    def _matrix(self, rows: list[dict], fit: bool):
        x_text = _HASHER.transform(self._texts(rows))
        cats = self._cats(rows)
        x_cat = self._dv.fit_transform(cats) if fit else self._dv.transform(cats)
        return hstack([x_text, x_cat]).tocsr()

    def fit(self, rows: list[dict], labels: list) -> "FindingClassifier":
        matrix = self._matrix(rows, fit=True)
        self._clf.fit(matrix, labels)
        self.classes_ = list(self._clf.classes_)
        self.n_samples = len(labels)
        return self

    def proba(self, rows: list[dict]) -> list[dict]:
        """One {class: probability} dict per row. Empty dicts if not fitted."""
        if not rows or not self.classes_:
            return [{} for _ in rows]
        matrix = self._matrix(rows, fit=False)
        probs = self._clf.predict_proba(matrix)
        return [dict(zip(self.classes_, row)) for row in probs]

    def predict_one(self, row: dict) -> tuple[Optional[object], float]:
        """(argmax label, its probability) for a single feature row."""
        out = self.proba([row])
        if not out or not out[0]:
            return None, 0.0
        dist = out[0]
        best = max(dist, key=dist.get)
        return best, float(dist[best])
