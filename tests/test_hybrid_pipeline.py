"""
Tests for the hybrid comparison pipeline (docs/hybrid-comparison-engine-implementation-plan.md).

These formalize the inline sanity scripts run during implementation (Phases 3-8) into a
permanent regression suite, plus real execution of crop_region_image's pixel math against
an actual PNG — that was reasoned through by hand during Phase 3 but never actually run,
which is the biggest verification gap flagged going into Phase 9.
"""
import io
import pytest
from unittest.mock import patch
from PIL import Image

from services.backend.infrastructure.audit.comparison.candidate import (
    ComparisonCandidate,
    calibrate_candidate_confidence,
)
from services.backend.infrastructure.audit.comparison.reconciler import reconcile_candidates
from services.backend.infrastructure.rendering.image_cropper import crop_region_image
from services.backend.infrastructure.storage.path_resolver import get_storage_root
from services.backend.infrastructure.audit.comparison.orchestrator import build_marking_table
import services.backend.infrastructure.audit.comparison.hybrid_orchestrator as ho
from services.backend.infrastructure.audit.comparison.reconciler import DisputedFinding
from services.backend.infrastructure.audit.comparison import crop_verifier as cv
from services.backend.infrastructure.audit.comparison.coordinate_resolver import harden_value_only_coordinates


def _candidate(text, status, x, y, bbox=None, category="drawing_views", origin="deterministic", feature=None):
    return ComparisonCandidate(
        text_content=text, status=status, details="d", category=category,
        origin=origin, coordinates=[x, y], bbox=bbox, resolution_method="entity_handle",
        feature=feature,
    )


# ─── reconciler.py ──────────────────────────────────────────────────────────────

def test_reconcile_agrees_within_radius():
    det = [_candidate("A", "CHANGED", 10.0, 10.0)]
    ai = [_candidate("A", "CHANGED", 12.0, 10.0, origin="ai_vision")]
    result = reconcile_candidates(det, ai)
    assert len(result.confirmed) == 1
    assert len(result.disputed) == 0


def test_reconcile_status_conflict_at_same_location():
    det = [_candidate("B", "CHANGED", 0.0, 0.0)]
    ai = [_candidate("B", "MATCHED", 0.0, 0.0, origin="ai_vision")]
    result = reconcile_candidates(det, ai)
    assert len(result.confirmed) == 0
    assert len(result.disputed) == 1
    assert result.disputed[0].det_candidate is not None
    assert result.disputed[0].ai_candidate is not None


def test_reconcile_mutual_single_source():
    det = [_candidate("C", "REMOVED", 100.0, 100.0)]
    ai = [_candidate("C", "REMOVED", 500.0, 500.0, origin="ai_vision")]  # far away
    result = reconcile_candidates(det, ai)
    assert len(result.confirmed) == 0
    assert len(result.disputed) == 2
    det_only = [d for d in result.disputed if d.det_candidate is not None and d.ai_candidate is None]
    ai_only = [d for d in result.disputed if d.ai_candidate is not None and d.det_candidate is None]
    assert len(det_only) == 1 and len(ai_only) == 1


def test_reconcile_category_mismatch_prevents_match_even_at_zero_distance():
    det = [_candidate("D", "MATCHED", 5.0, 5.0, category="drawing_views")]
    ai = [_candidate("D", "MATCHED", 5.0, 5.0, category="notes_section", origin="ai_vision")]
    result = reconcile_candidates(det, ai)
    assert len(result.confirmed) == 0
    assert len(result.disputed) == 2


# ─── hybrid_orchestrator.py::_confirmed_both_feature (checklist-taxonomy-grouping, ──
# ─── Phase 4 — confirmed-both `feature` tie-break, decision 5) ─────────────────────

def test_confirmed_both_feature_title_block_always_keeps_deterministic():
    det = _candidate("45", "MATCHED", 0.0, 0.0, category="title_block", feature="scale")
    ai = _candidate("45", "MATCHED", 0.0, 0.0, category="title_block", origin="ai_vision", feature="revision_code")
    assert ho._confirmed_both_feature(det, ai) == "scale"


def test_confirmed_both_feature_title_block_keeps_deterministic_even_when_other():
    det = _candidate("45", "MATCHED", 0.0, 0.0, category="title_block", feature="other")
    ai = _candidate("45", "MATCHED", 0.0, 0.0, category="title_block", origin="ai_vision", feature="revision_code")
    assert ho._confirmed_both_feature(det, ai) == "other"


def test_confirmed_both_feature_bill_of_materials_always_keeps_deterministic():
    det = _candidate("2", "MATCHED", 0.0, 0.0, category="bill_of_materials", feature="quantity")
    ai = _candidate("2", "MATCHED", 0.0, 0.0, category="bill_of_materials", origin="ai_vision", feature="material_type")
    assert ho._confirmed_both_feature(det, ai) == "quantity"


def test_confirmed_both_feature_drawing_views_keeps_deterministic_when_not_other():
    det = _candidate("R2", "MATCHED", 0.0, 0.0, category="drawing_views", feature="chamfer_radius")
    ai = _candidate("R2", "MATCHED", 0.0, 0.0, category="drawing_views", origin="ai_vision", feature="dimensions")
    assert ho._confirmed_both_feature(det, ai) == "chamfer_radius"


def test_confirmed_both_feature_drawing_views_falls_through_to_ai_when_deterministic_is_other():
    det = _candidate("R2", "MATCHED", 0.0, 0.0, category="drawing_views", feature="other")
    ai = _candidate("R2", "MATCHED", 0.0, 0.0, category="drawing_views", origin="ai_vision", feature="chamfer_radius")
    assert ho._confirmed_both_feature(det, ai) == "chamfer_radius"


def test_confirmed_both_feature_falls_through_when_deterministic_feature_is_none():
    det = _candidate("X", "MATCHED", 0.0, 0.0, category="notes_section", feature=None)
    ai = _candidate("X", "MATCHED", 0.0, 0.0, category="notes_section", origin="ai_vision", feature="special_notes")
    assert ho._confirmed_both_feature(det, ai) == "special_notes"


# ─── orchestrator.py::build_marking_table, reused by hybrid_orchestrator.py to ─
# ─── rebuild category tables from the FINAL reconciled/verified list ──────────

def test_build_marking_table_reflects_final_statuses_including_conflict():
    """
    This is the exact fix for the checklist panel showing Generator A's raw,
    pre-reconciliation guesses: hybrid_orchestrator.py now calls this same function
    against final_markings (post-reconciliation/verification) instead of relying on
    Generator A's own pre-built table. Confirms CONFLICT and a category filter both
    come through correctly.
    """
    markings = [
        {"text_content": "d", "status": "CONFLICT", "category": "drawing_views", "original_value": "d"},
        {"text_content": "Ø110", "status": "CHANGED", "category": "drawing_views", "original_value": "Ø90"},
        {"text_content": "24組", "status": "ADDED", "category": "title_block"},
        {"text_content": "No.", "status": "MATCHED", "category": "drawing_views"},
    ]
    table = build_marking_table(markings, category_filter="drawing_views")
    assert "CONFLICT" in table
    assert "CHANGED" in table
    assert "MATCHED" in table
    assert "24組" not in table  # title_block row filtered out
    assert table.count("\n") == 4  # header + separator + 3 drawing_views rows

    all_table = build_marking_table(markings)
    assert "24組" in all_table  # no filter -> includes title_block row too


def test_build_marking_table_empty_input_returns_empty_string():
    assert build_marking_table([], category_filter="drawing_views") == ""
    assert build_marking_table([{"text_content": "x", "status": "MATCHED", "category": "notes_section"}], category_filter="drawing_views") == ""


# ─── candidate.py::calibrate_candidate_confidence ──────────────────────────────

def test_confidence_ordering_is_monotonic():
    a = calibrate_candidate_confidence("confirmed_both", "deterministic", "entity_handle")
    b = calibrate_candidate_confidence("confirmed_single", "deterministic", "entity_handle")
    c = calibrate_candidate_confidence("confirmed_single", "ai_vision", "entity_handle")
    d = calibrate_candidate_confidence("unverified", "ai_vision", "entity_handle")
    e = calibrate_candidate_confidence("conflict", "deterministic", "entity_handle")
    assert a > b > c > d > e


def test_confidence_stays_within_bounds_at_worst_case():
    worst = calibrate_candidate_confidence("conflict", "ai_vision", "unresolved")
    assert 0.1 <= worst <= 1.0


def test_confidence_corrected_to_matched_ranks_between_confirmed_both_and_confirmed_single():
    both = calibrate_candidate_confidence("confirmed_both", "deterministic", "entity_handle")
    corrected = calibrate_candidate_confidence("corrected_to_matched", "deterministic", "entity_handle")
    single_det = calibrate_candidate_confidence("confirmed_single", "deterministic", "entity_handle")
    assert both > corrected > single_det


def test_confidence_resolution_method_penalizes_correctly():
    exact = calibrate_candidate_confidence("confirmed_both", "deterministic", "entity_handle")
    fallback = calibrate_candidate_confidence("confirmed_both", "deterministic", "visual_bbox_fallback")
    unresolved = calibrate_candidate_confidence("confirmed_both", "deterministic", "unresolved")
    assert exact > fallback > unresolved


# ─── hybrid_orchestrator.py helpers ─────────────────────────────────────────────

def test_describe_missing_and_present_candidate():
    assert ho._describe(None, "Deterministic generator") == (
        "NOT_FOUND", "Deterministic generator did not detect anything at this location."
    )
    cand = _candidate("X", "CHANGED", 1.0, 2.0)
    assert ho._describe(cand, "Deterministic generator") == ("CHANGED", "d")


def test_pick_cad_bbox_prefers_bbox_over_point_and_det_over_ai():
    det = _candidate("X", "CHANGED", 1.0, 2.0)
    ai = _candidate("X", "CHANGED", 9.0, 9.0, origin="ai_vision")
    assert ho._pick_cad_bbox(det, ai, side="rev") == (1.0, 2.0, 1.0, 2.0)
    assert ho._pick_cad_bbox(None, ai, side="rev") == (9.0, 9.0, 9.0, 9.0)
    assert ho._pick_cad_bbox(None, None, side="rev") is None

    det_with_bbox = _candidate("X", "CHANGED", 1.0, 2.0, bbox=[[0.0, 0.0], [5.0, 5.0]])
    assert ho._pick_cad_bbox(det_with_bbox, ai, side="rev") == (0.0, 0.0, 5.0, 5.0)


def test_resolve_disputed_covers_all_verdict_outcomes():
    det = _candidate("X", "CHANGED", 1.0, 2.0)
    ai = _candidate("X", "CHANGED", 9.0, 9.0, origin="ai_vision")
    f_both = DisputedFinding(finding_id="f1", det_candidate=det, ai_candidate=ai)
    f_det_only = DisputedFinding(finding_id="f2", det_candidate=None, ai_candidate=ai)

    m = ho._resolve_disputed(f_both, {"confirms": "A", "differs": True, "reasoning": "r"})
    assert m["verification"] == "confirmed_single" and m["status"] == "CHANGED" and m["origin"] == "deterministic"

    m = ho._resolve_disputed(f_both, {"confirms": "B", "differs": True, "reasoning": "r"})
    assert m["verification"] == "confirmed_single" and m["origin"] == "ai_vision"

    # Genuine ambiguity: the verifier agrees something really differs (differs=True) but
    # can't confirm which generator's account matches -> CONFLICT.
    m = ho._resolve_disputed(f_both, {"confirms": "neither", "differs": True, "reasoning": "r"})
    assert m["verification"] == "conflict" and m["status"] == "CONFLICT"

    m = ho._resolve_disputed(f_both, None)
    assert m["verification"] == "conflict" and m["status"] == "CONFLICT"

    # verdict names a side that doesn't exist for this finding -> still CONFLICT, never
    # silently falls back to the side that does exist as if it had been confirmed
    m = ho._resolve_disputed(f_det_only, {"confirms": "A", "differs": True, "reasoning": "r"})
    assert m["verification"] == "conflict" and m["status"] == "CONFLICT"


def test_resolve_disputed_differs_false_overrides_to_matched():
    """
    differs=False must win over whatever `confirms` says (and must be checked even when
    confirms is missing/"neither") — the verifier looked at the real crops and found no
    actual difference, which overrides both generators' original claims rather than
    landing as a review-worthy CONFLICT. This is the fix for the bug where nearly every
    disputed finding in a real hybrid run resolved to CONFLICT even when the crops were
    visually identical, because `differs` was collected from the verifier and never read.
    """
    det = _candidate("X", "REMOVED", 1.0, 2.0)
    finding = DisputedFinding(finding_id="f1", det_candidate=det, ai_candidate=None)

    # differs=False alongside confirms="neither" (the realistic shape for a single-source
    # dispute where the verifier just says "nothing to confirm, and nothing differs")
    m = ho._resolve_disputed(finding, {"confirms": "neither", "differs": False, "reasoning": "still there in both crops"})
    assert m["verification"] == "corrected_to_matched"
    assert m["status"] == "MATCHED"

    # differs=False should win even if confirms names a side — "no difference" is a
    # stronger, more specific claim than "confirm side A/B", so it takes priority.
    m = ho._resolve_disputed(finding, {"confirms": "A", "differs": False, "reasoning": "r"})
    assert m["verification"] == "corrected_to_matched"
    assert m["status"] == "MATCHED"


def test_pick_cad_bbox_falls_back_to_other_side_for_removed_and_added_items():
    """
    A REMOVED candidate has no rev-side geometry by definition (it doesn't exist on the
    revision) — side="rev" must fall back to the ref-side geometry so the verifier has
    something to actually look at, instead of getting None and "(no revision crop
    available)". Mirrors the real production data: 34 of 59 CONFLICT findings in one
    real hybrid run had rev_geom=False before this fix.
    """
    removed_det = _candidate("d", "REMOVED", 0.0, 0.0)  # coordinates set by _candidate helper...
    removed_det.coordinates = None  # ...but a real REMOVED candidate never has rev-side coordinates
    removed_det.ref_coordinates = [519.0, 309.9]

    # Natural side (rev) has nothing -> falls back to ref-side coordinates
    assert ho._pick_cad_bbox(removed_det, None, side="rev") == (519.0, 309.9, 519.0, 309.9)
    # ref side still resolves normally (no fallback needed)
    assert ho._pick_cad_bbox(removed_det, None, side="ref") == (519.0, 309.9, 519.0, 309.9)

    # Symmetric case: an ADDED candidate has no ref-side geometry
    added_det = _candidate("45", "ADDED", 35.0, 273.0)
    added_det.ref_coordinates = None
    assert ho._pick_cad_bbox(added_det, None, side="ref") == (35.0, 273.0, 35.0, 273.0)
    assert ho._pick_cad_bbox(added_det, None, side="rev") == (35.0, 273.0, 35.0, 273.0)

    # Both sides genuinely empty -> still None, no fallback possible
    empty = _candidate("x", "REMOVED", 0.0, 0.0)
    empty.coordinates = None
    empty.ref_coordinates = None
    assert ho._pick_cad_bbox(empty, None, side="rev") is None


# ─── crop_verifier.py::run_crop_verification (async, concurrent batching) ─────

def _mk_input(finding_id: str) -> cv.CropVerificationInput:
    return cv.CropVerificationInput(
        finding_id=finding_id, ref_crop=None, rev_crop=None,
        det_status="REMOVED", det_details="d", ai_status="NOT_FOUND", ai_details="d",
    )


@pytest.mark.asyncio
async def test_run_crop_verification_batches_and_merges_results():
    """
    Was a synchronous, sequential for-loop calling a blocking Gemini SDK function
    directly — with ~8 batches for a real drawing pair, that stalled the entire
    FastAPI event loop for the full sequential duration, not just this one request,
    and was the direct cause of the frontend's fetch timing out on drawing pairs with
    many disputed findings. Now async, batches run concurrently (bounded by
    MAX_CONCURRENT_BATCHES) via asyncio.to_thread. This confirms batching and result
    merging are still correct after that rewrite — a call count assertion is the
    simplest reliable signal that batching by MAX_BATCH_SIZE actually happened.
    """
    inputs = [_mk_input(f"f{i}") for i in range(cv.MAX_BATCH_SIZE * 2 + 3)]  # 3 batches worth

    call_batches: list[int] = []

    def fake_execute(api_key, batch):
        call_batches.append(len(batch))
        return {f.finding_id: {"confirms": "A", "differs": True, "reasoning": "r"} for f in batch}

    with patch.object(cv, "execute_crop_verification", side_effect=fake_execute):
        results = await cv.run_crop_verification("fake-key", inputs)

    assert len(results) == len(inputs)
    assert all(v["confirms"] == "A" for v in results.values())
    assert sorted(call_batches) == [3, cv.MAX_BATCH_SIZE, cv.MAX_BATCH_SIZE]


@pytest.mark.asyncio
async def test_run_crop_verification_isolates_a_failed_batch():
    """
    One batch raising must not crash the whole call or drop the other batches'
    results — its findings are simply absent, which hybrid_orchestrator.py's
    _resolve_disputed treats as a missing verdict (-> CONFLICT), not a fabricated one.
    """
    good_inputs = [_mk_input("good1"), _mk_input("good2")]
    bad_inputs = [_mk_input("bad1")]

    def fake_execute(api_key, batch):
        if batch[0].finding_id.startswith("bad"):
            raise RuntimeError("simulated Gemini failure")
        return {f.finding_id: {"confirms": "A", "differs": True, "reasoning": "r"} for f in batch}

    original_batch_size = cv.MAX_BATCH_SIZE
    cv.MAX_BATCH_SIZE = 2  # force good_inputs and bad_inputs into separate batches
    try:
        with patch.object(cv, "execute_crop_verification", side_effect=fake_execute):
            results = await cv.run_crop_verification("fake-key", good_inputs + bad_inputs)
    finally:
        cv.MAX_BATCH_SIZE = original_batch_size

    assert set(results.keys()) == {"good1", "good2"}
    assert "bad1" not in results


@pytest.mark.asyncio
async def test_run_crop_verification_logs_summary_with_correct_counts(caplog):
    """
    The summary log line (added alongside the MAX_BATCH_SIZE/MAX_CONCURRENT_BATCHES
    tuning) is what turns "placeholder, tune later" into something measurable against
    real hybrid runs — this locks down that it reports the right batch count, the right
    verified/submitted split (the delta is the CONFLICT-dropout count), and the right
    failed-batch count on a mix of successful and failed mocked batches.
    """
    good_inputs = [_mk_input("good1"), _mk_input("good2")]
    bad_inputs = [_mk_input("bad1")]

    def fake_execute(api_key, batch):
        if batch[0].finding_id.startswith("bad"):
            raise RuntimeError("simulated Gemini failure")
        return {f.finding_id: {"confirms": "A", "differs": True, "reasoning": "r"} for f in batch}

    original_batch_size = cv.MAX_BATCH_SIZE
    cv.MAX_BATCH_SIZE = 2  # force good_inputs and bad_inputs into separate batches
    try:
        with patch.object(cv, "execute_crop_verification", side_effect=fake_execute):
            with caplog.at_level("INFO"):
                results = await cv.run_crop_verification("fake-key", good_inputs + bad_inputs)
    finally:
        cv.MAX_BATCH_SIZE = original_batch_size

    assert len(results) == 2
    summary_lines = [r.message for r in caplog.records if "batch(es)" in r.message and "findings verified" in r.message]
    assert len(summary_lines) == 1
    summary = summary_lines[0]
    assert "2 batch(es)" in summary
    assert "2/3 findings verified" in summary
    assert "1 batch(es) failed outright" in summary


# ─── image_cropper.py::crop_region_image (real PNG, real pixel math) ──────────

@pytest.fixture
def synthetic_rendering():
    """
    Writes a real 1000x1000 PNG to storage/renderings/ so crop_region_image runs its
    actual PIL crop against real pixels, not just the hand-reasoned math from Phase 3's
    completion log. render_bounds maps CAD [0,0]-[100,100] onto the full 1000x1000 image,
    i.e. 1 CAD unit == 10 px. Cleans up after itself regardless of test outcome.
    """
    drawing_id = "test_hybrid_crop_fixture"
    render_path = get_storage_root() / "renderings" / f"{drawing_id}.png"
    render_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1000, 1000), color="white")
    img.save(render_path, format="PNG")
    metadata = {"render_bounds": [0.0, 0.0, 100.0, 100.0]}
    yield drawing_id, metadata
    if render_path.exists():
        render_path.unlink()


def test_crop_region_image_exact_bbox_no_margin(synthetic_rendering):
    drawing_id, metadata = synthetic_rendering
    # CAD bbox [40,40]-[60,60], no padding -> pixel box should be exactly (400,400)-(600,600)
    result = crop_region_image(drawing_id, metadata, (40.0, 40.0, 60.0, 60.0), margin_pct=0.0)
    assert result is not None
    cropped = Image.open(io.BytesIO(result))
    assert cropped.size == (200, 200)


def test_crop_region_image_applies_margin_padding(synthetic_rendering):
    drawing_id, metadata = synthetic_rendering
    # Same bbox, 50% margin on a 20-unit-wide box -> +/-10 units each side -> 40-unit-wide
    # region -> 400px crop (vs. 200px unpadded above).
    result = crop_region_image(drawing_id, metadata, (40.0, 40.0, 60.0, 60.0), margin_pct=0.5)
    assert result is not None
    cropped = Image.open(io.BytesIO(result))
    assert cropped.size == (400, 400)


def test_crop_region_image_point_bbox_gets_floor_padding(synthetic_rendering):
    drawing_id, metadata = synthetic_rendering
    # A zero-area point (a marking's bare coordinate, not a real region) still needs a
    # usable crop window -- the 1.0 CAD-unit floor in crop_region_image should kick in.
    result = crop_region_image(drawing_id, metadata, (50.0, 50.0, 50.0, 50.0), margin_pct=0.15)
    assert result is not None
    cropped = Image.open(io.BytesIO(result))
    assert cropped.size[0] > 0 and cropped.size[1] > 0


def test_crop_region_image_falls_back_without_bbox(synthetic_rendering):
    drawing_id, metadata = synthetic_rendering
    result = crop_region_image(drawing_id, metadata, None, margin_pct=0.0)
    assert result is not None
    cropped = Image.open(io.BytesIO(result))
    # Bottom-right-quadrant fallback: 70%-100% of a 1000x1000 image -> 300x300
    assert cropped.size == (300, 300)


def test_crop_region_image_falls_back_without_render_bounds():
    drawing_id = "test_hybrid_crop_fixture_no_bounds"
    render_path = get_storage_root() / "renderings" / f"{drawing_id}.png"
    render_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (500, 500), color="white").save(render_path, format="PNG")
    try:
        result = crop_region_image(drawing_id, {}, (10.0, 10.0, 20.0, 20.0), margin_pct=0.0)
        assert result is not None
        cropped = Image.open(io.BytesIO(result))
        assert cropped.size == (150, 150)  # 70%-100% of 500px
    finally:
        if render_path.exists():
            render_path.unlink()


def test_crop_region_image_missing_rendering_returns_none():
    result = crop_region_image("nonexistent_drawing_id_xyz", {"render_bounds": [0, 0, 10, 10]}, (1.0, 1.0, 2.0, 2.0))
    assert result is None


# ─── coordinate_resolver.py::harden_value_only_coordinates (checklist-taxonomy-────
# ─── grouping, Phase 7 — value-only-coordinate safety net, decision 7) ───────────

class _FakeEntity:
    """Duck-typed stand-in for ExtractedEntity — coordinate_resolver.py only ever
    reads .entity_type/.properties/.geometry via getattr, so a real Beanie Document
    (which needs an initialized DB collection to even construct) isn't required."""
    def __init__(self, entity_type, properties, geometry):
        self.entity_type = entity_type
        self.properties = properties
        self.geometry = geometry


def _label_entity(text, x, y, w=10.0, h=4.0):
    return _FakeEntity(
        entity_type="text",
        properties={"text": text, "height": 3.0, "bbox": [[x, y], [x + w, y + h]]},
        geometry={"insert": [x, y]},
    )


def test_harden_value_only_coordinates_nulls_coordinate_coincident_with_label():
    # "SCALE" label anchor (bbox-based formula): [x + bbox_w + height*0.8, y + bbox_h/2]
    # = [0 + 10 + 2.4, 0 + 2.0] = [12.4, 2.0]
    rev_entities = [_label_entity("SCALE", 0.0, 0.0)]
    ref_entities = [_label_entity("SCALE", 0.0, 0.0)]
    markings = [
        {"category": "title_block", "coordinates": [12.4, 2.0], "ref_coordinates": [12.4, 2.0]},
    ]
    harden_value_only_coordinates(markings, ref_entities, rev_entities)
    assert markings[0]["coordinates"] is None
    assert markings[0]["ref_coordinates"] is None


def test_harden_value_only_coordinates_leaves_genuine_value_coordinate_untouched():
    rev_entities = [_label_entity("SCALE", 0.0, 0.0)]
    ref_entities = [_label_entity("SCALE", 0.0, 0.0)]
    markings = [
        {"category": "title_block", "coordinates": [500.0, 500.0], "ref_coordinates": [500.0, 500.0]},
    ]
    harden_value_only_coordinates(markings, ref_entities, rev_entities)
    assert markings[0]["coordinates"] == [500.0, 500.0]
    assert markings[0]["ref_coordinates"] == [500.0, 500.0]


def test_harden_value_only_coordinates_ignores_non_title_block_bom_categories():
    rev_entities = [_label_entity("SCALE", 0.0, 0.0)]
    ref_entities = [_label_entity("SCALE", 0.0, 0.0)]
    markings = [
        {"category": "drawing_views", "coordinates": [12.4, 2.0], "ref_coordinates": [12.4, 2.0]},
    ]
    harden_value_only_coordinates(markings, ref_entities, rev_entities)
    assert markings[0]["coordinates"] == [12.4, 2.0]
    assert markings[0]["ref_coordinates"] == [12.4, 2.0]


def test_harden_value_only_coordinates_applies_to_bill_of_materials_too():
    rev_entities = [_label_entity("Q'ty", 0.0, 0.0)]
    ref_entities = [_label_entity("Q'ty", 0.0, 0.0)]
    markings = [
        {"category": "bill_of_materials", "coordinates": [12.4, 2.0], "ref_coordinates": None},
    ]
    harden_value_only_coordinates(markings, ref_entities, rev_entities)
    assert markings[0]["coordinates"] is None
