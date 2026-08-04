"""Tests for apply_learned_adjustments — the post-cache learned overlay on a comparison.

Covers: the model flips a false-alarm CHANGED to MATCHED and the recomputed drawing_views
rollup reflects it; an exact human override wins even when the generalizing model is not
trained; the confidence gates abstain (verdict unchanged) when closed; and a totally untrained
system is a no-op.
"""
from types import SimpleNamespace

import pytest

from services.backend.api.schemas import CanvasMarking, CategoryComparison, PhysicalComparisonResponse
from services.backend.infrastructure.learning import config, model_holder, trainer
from services.backend.infrastructure.learning.inference import apply_learned_adjustments
from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager


def _cc(status="MATCHED"):
    return CategoryComparison(status=status, difference_summary="", reference_content="",
                              revision_content="", engineering_discrepancy_details="")


def _response(markings):
    return PhysicalComparisonResponse(
        drawing_views=_cc("CHANGED"), notes_section=_cc(), bill_of_materials=_cc(),
        title_block=_cc(), isometric_view=_cc(), other_engineering_references=_cc(),
        canvas_markings=markings,
    )


def _fake_doc(status, rev, ref=None, category="drawing_views", feature="other", numeric=False, corrected_category=None):
    return SimpleNamespace(
        human_corrected_status=status, category=category, entity_text=rev,
        original_status="CHANGED", corrected_category=corrected_category, corrected_value=None,
        created_at=None,
        finding_snapshot={
            "rev_text": rev, "ref_text": ref if ref is not None else rev, "det_status": "CHANGED",
            "category": category, "feature": feature,
            "text_similarity": 1.0 if (ref is None or ref == rev) else 0.1,
            "match_distance": 0.2, "is_numericish": numeric,
        },
    )


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(VaultSyncManager.get_instance(), "vault_path", tmp_path)
    model_holder.LearnedModelHolder._instance = None
    yield
    model_holder.LearnedModelHolder._instance = None


def _install(docs):
    bundle = trainer.build_bundle(docs)
    model_holder.save_bundle(bundle)
    holder = model_holder.LearnedModelHolder.get_instance()
    holder.reload()
    return holder


def test_model_flips_false_alarm_to_matched(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRAIN", 8)
    docs = [_fake_doc("dismissed", f"LEGEND NOTE {i}", ref=f"LEGEND NOTE {i}") for i in range(10)]
    docs += [_fake_doc("confirmed_change", str(100 + i), ref=str(50 + i), feature="dimension", numeric=True) for i in range(10)]
    holder = _install(docs)
    assert holder.verdict_ready()

    # A legend-like CHANGED finding NOT in the exact-override set (id 999) — only the model can act.
    m = CanvasMarking(text_content="LEGEND NOTE 999", original_value="LEGEND NOTE 999",
                      status="CHANGED", details="d", category="drawing_views")
    out = apply_learned_adjustments(_response([m]))
    assert out.canvas_markings[0].status == "MATCHED"
    assert out.drawing_views.status == "MATCHED"       # rollup recomputed from adjusted markings


def test_exact_override_forces_matched_even_when_model_not_ready(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRAIN", 1000)     # model can never be ready
    holder = _install([_fake_doc("verdict_matched", "SPECIAL LEGEND", ref="SPECIAL LEGEND")])
    assert not holder.verdict_ready()

    m = CanvasMarking(text_content="SPECIAL LEGEND", status="CHANGED", details="d", category="drawing_views")
    out = apply_learned_adjustments(_response([m]))
    assert out.canvas_markings[0].status == "MATCHED"  # exact human correction wins regardless


def test_low_confidence_abstains(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRAIN", 8)
    monkeypatch.setattr(config, "LOW_THRESH", 0.0)     # gate closed: never suppress
    monkeypatch.setattr(config, "HIGH_THRESH", 1.0)    # gate closed: never promote
    docs = [_fake_doc("dismissed", f"LEGEND {i}", ref=f"LEGEND {i}") for i in range(8)]
    docs += [_fake_doc("confirmed_change", str(100 + i), ref=str(i), numeric=True) for i in range(8)]
    _install(docs)

    m = CanvasMarking(text_content="LEGEND 999", original_value="LEGEND 999",
                      status="CHANGED", details="d", category="drawing_views")
    out = apply_learned_adjustments(_response([m]))
    assert out.canvas_markings[0].status == "CHANGED"  # gates closed -> abstain, deterministic verdict kept


def test_untrained_system_is_noop():
    m = CanvasMarking(text_content="ANYTHING", status="CHANGED", details="d", category="drawing_views")
    out = apply_learned_adjustments(_response([m]))
    assert out.canvas_markings[0].status == "CHANGED"
