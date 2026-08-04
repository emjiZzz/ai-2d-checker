"""Tests for the learned-correction classifier + trainer.

Covers: feature-row shape stability (train/runtime must agree), that a fitted classifier
separates false-alarms from real changes, that the trainer abstains (verdict_clf=None) below
MIN_TRAIN while still capturing exact overrides immediately, and that the bundle round-trips
through joblib into the vault directory.
"""
from types import SimpleNamespace

from services.backend.infrastructure.learning import feature_extractor as fe
from services.backend.infrastructure.learning import config, model_holder, trainer
from services.backend.infrastructure.learning.finding_classifier import FindingClassifier
from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager


def _row0():
    # "Legend"-style static callout that a human keeps dismissing -> not a real change.
    return fe.build_feature_row("STATIC LEGEND", "STATIC LEGEND", "CHANGED", "drawing_views", "other",
                                text_similarity=1.0, match_distance=0.1, is_numericish=False)


def _row1(i=0):
    # A dimension that genuinely changed value -> a real discrepancy.
    return fe.build_feature_row(str(10 + i), str(80 + i), "CHANGED", "drawing_views", "dimension",
                                text_similarity=0.1, match_distance=3.0, is_numericish=True)


def _fake_doc(status, rev, ref=None, category="drawing_views", feature="other", corrected_category=None):
    return SimpleNamespace(
        human_corrected_status=status, category=category, entity_text=rev,
        original_status="CHANGED", corrected_category=corrected_category, corrected_value=None,
        created_at=None,
        finding_snapshot={
            "rev_text": rev, "ref_text": ref if ref is not None else rev, "det_status": "CHANGED",
            "category": category, "feature": feature,
            "text_similarity": 1.0 if (ref is None or ref == rev) else 0.1,
            "match_distance": 0.2, "is_numericish": rev.isdigit(),
        },
    )


def test_feature_row_shape_stable():
    r = fe.features_from_marking({
        "text_content": "ø25", "status": "CHANGED", "category": "drawing_views",
        "feature": "hole", "original_value": "ø20", "coordinates": [1, 2], "ref_coordinates": [1, 3],
    })
    assert set(fe.CAT_NUM_KEYS).issubset(r.keys())
    assert r["is_numericish"] == 1
    assert 0.0 <= r["text_similarity"] <= 1.0
    assert "||" in r["text_combined"]


def test_proba_empty_when_unfitted():
    assert FindingClassifier().proba([{"text_combined": "x"}]) == [{}]


def test_train_predict_separates_classes():
    rows = [_row0() for _ in range(25)] + [_row1(i) for i in range(25)]
    labels = [0] * 25 + [1] * 25
    clf = FindingClassifier().fit(rows, labels)
    p_false = clf.proba([_row0()])[0].get(1, 0.0)
    p_true = clf.proba([_row1(99)])[0].get(1, 0.0)
    assert p_false < 0.5 < p_true


def test_build_bundle_abstains_below_min_train(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRAIN", 40)
    docs = [_fake_doc("dismissed", "LEGEND A"), _fake_doc("confirmed_change", "123")]
    bundle = trainer.build_bundle(docs)
    assert bundle["verdict_clf"] is None          # too few labels to train the model
    assert bundle["exact_matched"]                # but a single correction is remembered exactly
    assert bundle["n_total"] == 2


def test_bundle_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(VaultSyncManager.get_instance(), "vault_path", tmp_path)
    monkeypatch.setattr(config, "MIN_TRAIN", 6)
    model_holder.LearnedModelHolder._instance = None
    try:
        docs = [_fake_doc("dismissed", f"LEGEND {i}") for i in range(6)]
        docs += [_fake_doc("confirmed_change", str(100 + i)) for i in range(6)]
        bundle = trainer.build_bundle(docs)
        model_holder.save_bundle(bundle)

        holder = model_holder.LearnedModelHolder.get_instance()
        holder.reload()
        assert holder.bundle is not None
        assert holder.verdict_ready() is True
        assert (tmp_path / config.MODEL_DIRNAME / config.MODEL_FILENAME).exists()
    finally:
        model_holder.LearnedModelHolder._instance = None
