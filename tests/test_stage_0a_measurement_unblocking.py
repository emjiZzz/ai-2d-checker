"""Regression tests for Stage 0a of the AI maturity ladder — the three defects recorded in
`docs/vault/00 - AI Maturity Status.md` as actively poisoning any measurement taken before them.

Two were real and are pinned here. The third turned out not to be a defect at all, and the
test that says so is the most important one in the file: without it the ledger entry would be
"fixed" by someone computing those features in TypeScript, which is strictly worse than the
nulls it replaces (see test_finding_snapshot_nulls_are_recomputed_server_side).

See CLAUDE.md constraint 5.
"""
import inspect

import pytest

from services.backend.config import settings
from services.backend.infrastructure.audit.comparison import full_ai_orchestrator
from services.backend.infrastructure.learning.feature_extractor import (
    build_feature_row,
    features_from_marking,
    features_from_snapshot,
)


# ─── 0a.1 — generate_ai_vision_candidates referenced an undefined `request` ───────────────
#
# `client_name = getattr(request, "client_name", None)` sat inside a function whose signature
# has no `request`. Python resolves `request` at call time, so this raised NameError on every
# invocation. Its only caller is the `hybrid` method, and no `hybrid` cache entry has ever
# existed to mask it — so `hybrid` was 100% broken, silently, for as long as the line was there.


def test_ai_vision_generator_takes_client_name_as_a_parameter():
    sig = inspect.signature(full_ai_orchestrator.generate_ai_vision_candidates)
    assert "client_name" in sig.parameters, (
        "generate_ai_vision_candidates must accept client_name explicitly. It has no request "
        "object to read it off, and reading one anyway is what caused the NameError."
    )
    assert "request" not in sig.parameters, (
        "Adding a `request` parameter would fix the NameError the wrong way — this generator is "
        "deliberately request-free so the hybrid path can call it without an HTTP request."
    )


def test_ai_vision_generator_body_does_not_reference_a_free_request_name():
    """The bug class, not just the one line: any bare `request.` here is unresolvable."""
    source = inspect.getsource(full_ai_orchestrator.generate_ai_vision_candidates)
    assert "request" not in source.split('"""')[-1], (
        "generate_ai_vision_candidates references `request` outside its docstring, but has no "
        "such parameter — this is exactly the NameError Stage 0a fixed."
    )


# ─── 0a.2 — the standards AI pass was pinned to a retired model ───────────────────────────
#
# ai_engine.py hardcoded model="gemini-2.0-flash", shut down 2026-06-01 per config.py. Every
# call raised, and run_pass swallows its exception and returns [], so the pass reported "no
# violations" instead of failing. A measurement taken against that is a measurement of nothing.


def test_standards_pass_reads_the_model_from_settings():
    from services.backend.infrastructure.audit import ai_engine

    source = inspect.getsource(ai_engine)
    # The call-site form specifically — the prose above the fix names the retired model on
    # purpose, and a test that forbids naming it would forbid explaining it.
    assert 'model="gemini-2.0-flash"' not in source, (
        "gemini-2.0-flash was retired 2026-06-01 (config.py). Read settings.GEMINI_MODEL_* "
        "instead — every model string in this codebase is env-driven for this reason."
    )
    assert "settings.GEMINI_MODEL_PRO" in source


def test_configured_models_are_not_the_retired_one():
    for name in ("GEMINI_MODEL_PRO", "GEMINI_MODEL_FLASH", "GEMINI_MODEL_FALLBACK"):
        assert getattr(settings, name) != "gemini-2.0-flash", (
            f"settings.{name} points at a model Google shut down on 2026-06-01."
        )


# ─── 0a.3 — NOT a defect: null feature fields in FindingSnapshot ──────────────────────────
#
# The ledger recorded CorrectionControls.tsx hardcoding text_similarity / match_distance /
# is_numericish to null as label corruption that "cannot be retroactively repaired". It isn't.
# build_feature_row derives all three from the raw texts and coordinates whenever they arrive
# as None, and the INFERENCE path (features_from_marking) never supplies them at all — so null
# from the client is what keeps training and inference on one definition. Sending a
# TypeScript-computed similarity instead would be train/serve skew: JS has no SequenceMatcher
# and no SpatialDiffer._normalize_text.


def test_finding_snapshot_nulls_are_recomputed_server_side():
    snapshot = {
        "ref_text": "22.7±0.02",
        "rev_text": "22.7±0.05",
        "det_status": "CHANGED",
        "category": "drawing_views",
        "feature": "tolerance",
        "ref_coord": [100.0, 200.0],
        "rev_coord": [103.0, 204.0],
        # Exactly what the desktop client sends.
        "text_similarity": None,
        "match_distance": None,
        "is_numericish": None,
    }
    row = features_from_snapshot(snapshot)

    assert row["text_similarity"] > 0.5, "similarity must be derived from the two texts, not defaulted to 0"
    assert row["match_distance"] == pytest.approx(5.0), "distance must be derived from the two coordinates"
    assert row["is_numericish"] == 1, "numericish must be derived from the texts"


def test_training_and_inference_agree_on_the_derived_features():
    """The reason the nulls must stay: both phases must reach the same numbers.

    A MATCHED finding's marking and its snapshot describe the same finding, so the feature rows
    they produce must be identical. They are — because both let the server derive the three
    fields. A client-computed value would only ever appear on the training side.
    """
    marking = {
        "text_content": "⌀120",
        "original_value": "⌀120",
        "status": "MATCHED",
        "category": "drawing_views",
        "feature": "hole_properties",
        "ref_coordinates": [10.0, 20.0],
        "coordinates": [10.0, 20.0],
    }
    snapshot = {
        "ref_text": "⌀120",
        "rev_text": "⌀120",
        "det_status": "MATCHED",
        "category": "drawing_views",
        "feature": "hole_properties",
        "ref_coord": [10.0, 20.0],
        "rev_coord": [10.0, 20.0],
        "text_similarity": None,
        "match_distance": None,
        "is_numericish": None,
    }
    assert features_from_marking(marking) == features_from_snapshot(snapshot)


def test_an_explicitly_supplied_feature_still_wins():
    """The recompute is a fallback, not an override — a future caller that has better numbers
    (the differ itself, which already knows the true match distance) can still pass them."""
    row = build_feature_row(
        ref_text="abc", rev_text="xyz",
        det_status="CHANGED", category="notes_section", feature="other",
        text_similarity=0.75, match_distance=42.0, is_numericish=True,
        ref_coord=[0.0, 0.0], rev_coord=[1.0, 1.0],
    )
    assert row["text_similarity"] == pytest.approx(0.75)
    assert row["match_distance"] == pytest.approx(42.0)
    assert row["is_numericish"] == 1
