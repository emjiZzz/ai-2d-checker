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

# Minimum share of the *minority* verdict class before the head is allowed to activate.
# MIN_TRAIN alone is not a sufficient gate, and the corpus proved it: on 2026-08-11 it stood at
# 38/40 verdict labels split 28 class-0 / 10 class-1 — 74% negative — two `dismissed` clicks from
# switching itself on. `dismissed` is both the easiest correction to make and the most used, so
# the cheap path to 40 is also the most skewed one.
#
# Why skew is the danger and not merely a quality issue: a head trained on a 74%-negative prior
# centres its predictions near that prior, and `inference._decide` flips a deterministic
# CHANGED/ADDED/REMOVED to MATCHED whenever `p_true < LOW_THRESH`. A base rate that sits at or
# just above LOW_THRESH means ordinary findings cross the suppression gate on the prior alone —
# i.e. the model starts silently deleting real findings. That is the false-negative direction, in
# a system whose headline gap is that false negatives have never been measured.
#
# The default is tied to LOW_THRESH with margin (0.20 * 1.5): the minority class must be common
# enough that a calibrated prior sits clearly *above* the suppression gate rather than on it.
# Raise LOW_THRESH and this should move with it.
#
# Earn the balance with class-1 corrections (`confirmed_valid`, `verdict_changed`) rather than
# farming `dismissed`. See docs/vault/00 - AI Maturity Status.md, the "Learned model" row.
MIN_MINORITY_SHARE = _float("LEARNING_MIN_MINORITY_SHARE", 0.30)

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

# --- where the trained bundle lives (Stage 0h) -------------------------------------------
#
# It used to live only in the vault, under `09 - Learned Models/`. That directory is
# gitignored, so the model could not be committed, diffed, or shipped in the Tauri bundle —
# and a model that cannot be versioned is not trainable infrastructure. It blocked rung 3
# outright. See docs/vault/01 - Architecture/AI Maturity Ladder — Staged Plan.md, Stage 0h.
#
# Resolution order for *reads* is env -> storage -> vault; *writes* always go to the first
# two. The vault stays readable so an existing install keeps working until its next retrain,
# and is deprecated rather than removed.
MODEL_DIR_ENV = "LEARNED_MODEL_DIR"

# Relative to `services/backend/`. The `.joblib` payload is gitignored (it is a build
# artifact); the `.meta.json` beside it IS committed, so training runs are diffable in git
# without carrying a binary.
MODEL_STORAGE_DIRNAME = "storage/models"

# Deprecated read-only fallback. Still the home of `Model Card.md`, which is documentation
# for humans and belongs in the vault.
MODEL_DIRNAME = "09 - Learned Models"

MODEL_FILENAME = "finding_classifier.joblib"
META_FILENAME = "finding_classifier.meta.json"
CARD_FILENAME = "Model Card.md"

# Bump when the *meaning* of anything inside the bundle changes such that a previously trained
# bundle can no longer be read correctly. `LearnedModelHolder._read_bundle` refuses a mismatch
# and logs it, so a stale bundle reports itself rather than silently applying nothing — until
# 2026-08-17 this field was written and never read, which is the same inert-version-stamp gap
# CLAUDE.md records against `EXTRACTION_SCHEMA_VERSION`.
#
# v2: `exact_matched` / `exact_changed` are keyed by `exact_pair_key` (both sides of a finding,
#     `cat|ref->rev`) rather than `exact_key` (one side). A v1 bundle's keys are single values
#     and would never match a v2 lookup, so its overrides would be inert with no signal. The
#     next correction retrains and the keys are rebuilt from each row's stored snapshot.
BUNDLE_SCHEMA = 2
