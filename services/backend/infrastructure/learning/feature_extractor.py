"""Feature extraction for the learned-correction classifier.

Turns either a stored FindingSnapshot (captured at correction time, for TRAINING) or a live
CanvasMarking (produced at comparison time, for INFERENCE) into ONE canonical feature dict,
so the model sees identical inputs in both phases. Deliberately reuses SpatialDiffer's text
normalization and numeric-detection regex so "is this numeric" / "how similar are the two
texts" match the deterministic differ exactly rather than drifting into a second definition.
"""
from __future__ import annotations

import math
from difflib import SequenceMatcher
from typing import Any, Optional

# Reuse the exact normalization + numeric detector the deterministic differ uses. Both are
# module-level / static in spatial_differ; importing them does not pull the comparison pipeline.
from ..audit.comparison.spatial_differ import SpatialDiffer, _NUMERICISH_RE

# Keys handed to the DictVectorizer (categoricals one-hot, numerics passthrough). The free
# text lives separately under "text_combined" and is hashed, not dict-vectorized.
CAT_NUM_KEYS = (
    "det_status",
    "category",
    "feature",
    "text_similarity",
    "match_distance",
    "is_numericish",
    "len_ref",
    "len_rev",
)


def _norm(t: Optional[str]) -> str:
    if not t:
        return ""
    try:
        return SpatialDiffer._normalize_text(str(t))
    except Exception:
        return str(t).strip().lower()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _is_numericish(*vals: Optional[str]) -> bool:
    return any(bool(_NUMERICISH_RE.match(_norm(v))) for v in vals if v)


def _distance(p: Any, q: Any) -> float:
    """Euclidean distance between two [x, y] points; -1.0 when either is missing."""
    try:
        if not p or not q or len(p) < 2 or len(q) < 2:
            return -1.0
        return math.hypot(float(p[0]) - float(q[0]), float(p[1]) - float(q[1]))
    except (TypeError, ValueError, IndexError):
        return -1.0


def build_feature_row(
    ref_text: Optional[str],
    rev_text: Optional[str],
    det_status: Optional[str],
    category: Optional[str],
    feature: Optional[str],
    text_similarity: Optional[float] = None,
    match_distance: Optional[float] = None,
    is_numericish: Optional[bool] = None,
    ref_coord: Any = None,
    rev_coord: Any = None,
) -> dict:
    nref, nrev = _norm(ref_text), _norm(rev_text)
    if text_similarity is None:
        text_similarity = _similarity(nref, nrev)
    if match_distance is None:
        match_distance = _distance(ref_coord, rev_coord)
    if is_numericish is None:
        is_numericish = _is_numericish(ref_text, rev_text)
    return {
        "text_combined": f"{nref} || {nrev}".strip(),
        "det_status": str(det_status or "UNKNOWN"),
        "category": str(category or "unknown"),
        "feature": str(feature or "other"),
        "text_similarity": float(text_similarity or 0.0),
        "match_distance": float(match_distance if match_distance is not None else -1.0),
        "is_numericish": int(bool(is_numericish)),
        "len_ref": float(len(nref)),
        "len_rev": float(len(nrev)),
    }


def features_from_snapshot(snap: Optional[dict]) -> dict:
    """Feature row from a stored FindingSnapshot dict (training path)."""
    snap = snap or {}
    return build_feature_row(
        ref_text=snap.get("ref_text"),
        rev_text=snap.get("rev_text"),
        det_status=snap.get("det_status"),
        category=snap.get("category"),
        feature=snap.get("feature"),
        text_similarity=snap.get("text_similarity"),
        match_distance=snap.get("match_distance"),
        is_numericish=snap.get("is_numericish"),
        ref_coord=snap.get("ref_coord"),
        rev_coord=snap.get("rev_coord"),
    )


def features_from_marking(m: dict) -> dict:
    """Feature row from a live CanvasMarking dict (inference path).

    A marking's revision-side text is `text_content`; its reference-side text is
    `original_value` when the finding CHANGED, and the same text for MATCHED/REMOVED
    (which exist on the reference side unchanged). ADDED items have no reference text.
    """
    rev_text = m.get("text_content") or ""
    status = m.get("status")
    if m.get("original_value"):
        ref_text = m.get("original_value")
    elif status in ("MATCHED", "REMOVED"):
        ref_text = rev_text
    else:
        ref_text = ""
    return build_feature_row(
        ref_text=ref_text,
        rev_text=rev_text,
        det_status=status,
        category=m.get("category"),
        feature=m.get("feature"),
        ref_coord=m.get("ref_coordinates"),
        rev_coord=m.get("coordinates"),
    )


def exact_key(category: Optional[str], text: Optional[str]) -> str:
    """Stable key for exact-match correction memory: category + normalized text."""
    return f"{str(category or 'unknown')}|{_norm(text)}"
