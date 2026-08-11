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


def _skewed_docs(n_zero, n_one):
    return (
        [_fake_doc("dismissed", f"LEGEND {i}") for i in range(n_zero)]
        + [_fake_doc("confirmed_change", str(100 + i)) for i in range(n_one)]
    )


def test_build_bundle_holds_verdict_head_on_skewed_corpus(monkeypatch):
    """Reaching MIN_TRAIN the cheap way must NOT switch the head on.

    This pins the live 2026-08-11 corpus shape: 28 class-0 / 10 class-1, two `dismissed` clicks
    short of MIN_TRAIN. Those two clicks land at 30/10 — count met, 25% minority — and a head
    trained there centres its prior below LOW_THRESH, where `inference._decide` flips
    CHANGED/ADDED/REMOVED to MATCHED. That is silent suppression of real findings.
    """
    monkeypatch.setattr(config, "MIN_TRAIN", 40)
    monkeypatch.setattr(config, "MIN_MINORITY_SHARE", 0.30)

    bundle = trainer.build_bundle(_skewed_docs(30, 10))

    assert bundle["n_verdict"] == 40                      # the count gate is satisfied
    assert bundle["verdict_clf"] is None                  # and the head still must not activate
    abstained = bundle["metrics"]["verdict_abstained"]
    assert abstained["reason"] == "class_imbalance"
    assert abstained["minority_share"] == 0.25
    # The abstention has to be legible, not just correct — an invisible one is the failure mode
    # this codebase has already paid for once.
    assert "confirmed_valid" in abstained["detail"]


def test_build_bundle_activates_verdict_head_when_balanced(monkeypatch):
    """The guard must not be a permanent off switch — an honestly balanced corpus still trains."""
    monkeypatch.setattr(config, "MIN_TRAIN", 40)
    monkeypatch.setattr(config, "MIN_MINORITY_SHARE", 0.30)

    bundle = trainer.build_bundle(_skewed_docs(28, 12))    # 30% minority, exactly at the floor

    assert bundle["n_verdict"] == 40
    assert bundle["verdict_clf"] is not None
    assert "verdict_abstained" not in bundle["metrics"]
    assert bundle["metrics"]["verdict_minority_share"] == 0.30


def test_minority_share_floor_sits_above_the_suppression_gate():
    """The two constants are coupled: the balance floor exists to keep a calibrated prior clear of
    LOW_THRESH. If someone raises LOW_THRESH without moving the floor, the guard stops guarding."""
    assert config.MIN_MINORITY_SHARE > config.LOW_THRESH


def test_bundle_save_load_roundtrip(tmp_path, monkeypatch):
    # Stage 0h moved the artifact out of the vault, so redirecting `vault_path` no longer
    # contains a write — `learned_model_dir()` reads LEARNED_MODEL_DIR and otherwise lands
    # in `services/backend/storage/models/`. Without this env override the test writes a
    # 133 KB bundle into the working tree and the next run loads *it* instead of the real
    # one. Both are set: the vault redirect still contains the Model Card.
    monkeypatch.setenv(config.MODEL_DIR_ENV, str(tmp_path / "models"))
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
        assert (tmp_path / "models" / config.MODEL_FILENAME).exists()
        assert not (tmp_path / config.MODEL_DIRNAME / config.MODEL_FILENAME).exists(), (
            "The bundle must not be written into the vault — that is the situation "
            "Stage 0h exists to end."
        )
    finally:
        model_holder.LearnedModelHolder._instance = None
