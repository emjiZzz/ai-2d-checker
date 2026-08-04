"""Tunable knobs for the learned-correction layer. All overridable via env so behavior
can be tuned without a redeploy (mirrors how the rest of the backend reads settings)."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Minimum labeled corrections before the generalizing model is allowed to act at all.
# Below this the model abstains entirely (exact-match overrides still apply — a single
# correction always takes effect on that exact finding). This is the cold-start guard.
MIN_TRAIN = _int("LEARNING_MIN_TRAIN", 40)
CATEGORY_MIN_TRAIN = _int("LEARNING_CATEGORY_MIN_TRAIN", 40)

# Verdict gating. The verdict head predicts P(finding is a TRUE discrepancy).
#   P < LOW_THRESH   -> a deterministic CHANGED/ADDED/REMOVED is flipped to MATCHED (suppress noise)
#   P > HIGH_THRESH  -> a deterministic MATCHED is promoted to CHANGED (rarer, riskier; high bar)
LOW_THRESH = _float("LEARNING_LOW_THRESH", 0.20)
HIGH_THRESH = _float("LEARNING_HIGH_THRESH", 0.80)

# Category head confidence before an automatic reclassification is applied.
CATEGORY_CONF = _float("LEARNING_CATEGORY_CONF", 0.80)

# Only these three "spatial" categories are model-adjusted at inference in v1: they are the
# noisy ones (drawing_views/notes/iso) whose checklist content is a marking table we can
# regenerate consistently. title_block / bill_of_materials verdicts are table-derived with a
# different feature shape and are left to the deterministic logic in v1 (their corrections are
# still captured for training). See the vault gotcha note.
SPATIAL_CATEGORIES = ("drawing_views", "notes_section", "isometric_view")

# Vault storage (user decision: everything under the vault).
MODEL_DIRNAME = "09 - Learned Models"
MODEL_FILENAME = "finding_classifier.joblib"
META_FILENAME = "finding_classifier.meta.json"
CARD_FILENAME = "Model Card.md"

BUNDLE_SCHEMA = 1
