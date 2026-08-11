"""Phase 2: the coordinate contract.

Covers Blocker 3 — persisted coordinates were bare [x, y] arrays with no record of the
space they were measured in or the render bounds they were authored against, so a
re-render against different bounds silently displaced every stored pin with nothing
recording that it had happened.
"""

import math

import pytest

from services.backend.domain.models.annotation_document import AnnotationDocument
from services.backend.domain.models.audit_violation import AuditViolation
from services.backend.domain.models.cad_point import (
    CadPoint,
    coerce_cad_point,
    coerce_cad_point_list,
)
from services.backend.infrastructure.cad.coordinate_stamp import (
    has_drifted,
    stamp_cad_point,
    stamp_pair,
)
from services.backend.infrastructure.cad.viewport_transform import (
    NO_VIEWPORT,
    TRANSFORM_VERSION,
    Viewport,
    ViewportTransform,
)

EPSILON = 1e-6


@pytest.fixture(autouse=True)
def uninitialized_beanie_documents(monkeypatch):
    """Let Beanie Documents be constructed without a live MongoDB.

    These tests exercise field validation only, but Document.__init__ resolves the
    pymongo collection eagerly. Same approach as tests/test_phase3_cad_pipeline.py.
    """
    from unittest.mock import MagicMock

    for model in (AnnotationDocument, AuditViolation):
        monkeypatch.setattr(model, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))


class FakeDrawing:
    """Stands in for a DrawingDocument; only `metadata` is read when stamping."""

    def __init__(self, metadata=None):
        self.metadata = metadata or {}


def _transform() -> ViewportTransform:
    return ViewportTransform(
        "Layout1",
        [
            Viewport(
                index=0, handle="VP0",
                paper_center_x=200.0, paper_center_y=150.0,
                paper_width=300.0, paper_height=200.0,
                view_anchor_x=50.0, view_anchor_y=25.0,
                view_height=100.0, scale=2.0,
            )
        ],
    )


def _paper_drawing() -> FakeDrawing:
    return FakeDrawing({
        "coordinate_space": "paper",
        "transform_version": TRANSFORM_VERSION,
        "viewport_transform": _transform().to_dict(),
        "render_bounds": [0.0, 0.0, 400.0, 300.0],
    })


# --------------------------------------------------------------------------
# Coercion — the several shapes producers actually pass
# --------------------------------------------------------------------------

def test_coerce_accepts_bare_pair():
    point = coerce_cad_point([10.0, 20.0])
    assert point is not None
    assert (point.x, point.y) == (10.0, 20.0)
    # Unqualified by default rather than falsely claiming a space.
    assert point.space == "render"
    assert point.viewport_index == NO_VIEWPORT


def test_coerce_accepts_dict_and_passthrough():
    from_dict = coerce_cad_point({"x": 1.0, "y": 2.0, "space": "paper"})
    assert from_dict is not None and from_dict.space == "paper"

    existing = CadPoint(x=3.0, y=4.0, space="model")
    assert coerce_cad_point(existing) is existing


@pytest.mark.parametrize("bad", [None, "nope", [], [1.0], {"x": "a", "y": "b"}])
def test_coerce_rejects_unusable_input(bad):
    assert coerce_cad_point(bad) is None


def test_coerce_list_handles_every_producer_shape():
    """The ~8 AuditViolation producers pass a mix of shapes: a single unwrapped [x, y]
    (title_block_rules, row_extractor), a list of pairs (layer_rules), and already
    stamped CadPoints (persistence_handler)."""
    single_pair = coerce_cad_point_list([10.0, 20.0])
    assert single_pair is not None and len(single_pair) == 1
    assert (single_pair[0].x, single_pair[0].y) == (10.0, 20.0)

    pair_list = coerce_cad_point_list([[1.0, 2.0], [3.0, 4.0]])
    assert pair_list is not None and len(pair_list) == 2

    stamped = coerce_cad_point_list([CadPoint(x=5.0, y=6.0)])
    assert stamped is not None and len(stamped) == 1

    assert coerce_cad_point_list(None) is None
    assert coerce_cad_point_list([]) is None


def test_three_dimensional_point_keeps_only_xy():
    """layer_rules passes `ent.geometry.get("start")`, which is [x, y, z]."""
    point = coerce_cad_point([1.0, 2.0, 3.0])
    assert point is not None
    assert (point.x, point.y) == (1.0, 2.0)


# --------------------------------------------------------------------------
# Stamping — provenance filled server-side, not trusted from the client
# --------------------------------------------------------------------------

def test_stamp_captures_full_provenance():
    point = stamp_cad_point(150.0, 120.0, _paper_drawing())
    assert point.space == "paper"
    assert point.layout == "Layout1"
    assert point.transform_version == TRANSFORM_VERSION
    assert point.bounds == [0.0, 0.0, 400.0, 300.0]
    # Resolved by asking the transform which viewport's paper rect contains the point.
    assert point.viewport_index == 0


def test_stamp_defaults_to_render_space_for_pdf_style_drawings():
    """PDF ingestion measures against the PyMuPDF page rect -- neither model nor paper."""
    point = stamp_cad_point(10.0, 20.0, FakeDrawing({"render_bounds": [0, 0, 100, 100]}))
    assert point.space == "render"
    assert point.viewport_index == NO_VIEWPORT
    assert point.layout is None


def test_stamp_tolerates_a_missing_drawing():
    point = stamp_cad_point(1.0, 2.0, None)
    assert (point.x, point.y) == (1.0, 2.0)
    assert point.space == "render"


def test_stamped_point_inverts_to_model_space():
    """The reason provenance is captured: a stored point must be mappable back into the
    source file's model space for CAD writeback."""
    drawing = _paper_drawing()
    transform = _transform()

    authored = transform.project(50.0, 25.0)
    point = stamp_cad_point(authored.x, authored.y, drawing)

    restored = ViewportTransform.from_dict(drawing.metadata["viewport_transform"])
    back = restored.unproject(point.x, point.y, point.viewport_index)
    assert math.isclose(back.x, 50.0, abs_tol=EPSILON)
    assert math.isclose(back.y, 25.0, abs_tol=EPSILON)


# --------------------------------------------------------------------------
# Drift detection — the situation that used to be silent
# --------------------------------------------------------------------------

def test_no_drift_when_bounds_are_unchanged():
    drawing = _paper_drawing()
    point = stamp_cad_point(150.0, 120.0, drawing)
    assert has_drifted(point, drawing) is False


def test_drift_detected_when_the_drawing_is_rerendered():
    drawing = _paper_drawing()
    point = stamp_cad_point(150.0, 120.0, drawing)

    # A different layout becomes the render target on re-ingest.
    drawing.metadata["render_bounds"] = [0.0, 0.0, 841.0, 594.0]
    assert has_drifted(point, drawing) is True


def test_drift_is_false_when_either_side_is_unknown():
    """Absence of evidence is not drift."""
    unstamped = CadPoint(x=1.0, y=2.0)
    assert has_drifted(unstamped, _paper_drawing()) is False
    assert has_drifted(None, _paper_drawing()) is False
    assert has_drifted(stamp_cad_point(1.0, 2.0, _paper_drawing()), FakeDrawing()) is False


def test_stamp_pair_passes_through_existing_envelopes():
    existing = CadPoint(x=9.0, y=9.0, space="model")
    assert stamp_pair(existing, _paper_drawing()) is existing
    assert stamp_pair(None, _paper_drawing()) is None
    assert stamp_pair([1.0, 2.0], _paper_drawing()) is not None


# --------------------------------------------------------------------------
# The documents themselves
# --------------------------------------------------------------------------

def test_annotation_document_coerces_a_bare_pair():
    """Safety net for any writer that bypasses the router's stamping."""
    annotation = AnnotationDocument(
        review_session_id="r1", drawing_id="d1", author_id="tester",
        annotation_type="pin", content="check this",
        coordinates=[12.5, 34.5],
    )
    assert isinstance(annotation.coordinates, CadPoint)
    assert (annotation.coordinates.x, annotation.coordinates.y) == (12.5, 34.5)


def test_annotation_document_accepts_a_stamped_point():
    point = stamp_cad_point(150.0, 120.0, _paper_drawing())
    annotation = AnnotationDocument(
        review_session_id="r1", drawing_id="d1", author_id="tester",
        annotation_type="pin", content="check this", coordinates=point,
    )
    assert annotation.coordinates is not None
    assert annotation.coordinates.space == "paper"
    assert annotation.coordinates.viewport_index == 0


def test_annotation_document_allows_no_coordinates():
    annotation = AnnotationDocument(
        review_session_id="r1", drawing_id="d1", author_id="tester",
        annotation_type="note", content="general remark",
    )
    assert annotation.coordinates is None


@pytest.mark.parametrize(
    "raw",
    [
        [10.0, 20.0],                       # title_block_rules / row_extractor
        [[10.0, 20.0], [30.0, 40.0]],       # layer_rules
        [CadPoint(x=10.0, y=20.0)],         # persistence_handler
        [[10.0, 20.0, 0.0]],                # geometry with a z component
    ],
)
def test_audit_violation_coerces_every_producer_shape(raw):
    violation = AuditViolation(
        audit_session_id="s1", severity="medium", category="test",
        description="d", recommendation="r", source="rule_engine",
        coordinates=raw,
    )
    assert violation.coordinates is not None
    assert all(isinstance(p, CadPoint) for p in violation.coordinates)
    assert (violation.coordinates[0].x, violation.coordinates[0].y) == (10.0, 20.0)


def test_audit_violation_allows_no_coordinates():
    violation = AuditViolation(
        audit_session_id="s1", severity="low", category="test",
        description="d", recommendation="r", source="rule_engine",
    )
    assert violation.coordinates is None


# --------------------------------------------------------------------------------------
# view_anchor: the rename, and the per-view origin it makes legible
# --------------------------------------------------------------------------------------


def test_a_stored_transform_using_the_legacy_view_center_key_still_loads():
    """Every drawing extracted before 2026-08-11 persisted this value as `view_center`.

    The rename is cosmetic and TRANSFORM_VERSION deliberately did not move, so `from_dict`
    has to keep reading the old spelling. If it stopped, the anchor would resolve to (0,0)
    rather than raise -- and the projection would be silently wrong by the anchor's
    magnitude on every drawing already in MongoDB. On M745221N01_FSRS2 that is ~250 units,
    which puts a view's origin clean off the printed sheet while every number involved
    stays finite and plausible.
    """
    legacy = {
        "index": 0, "handle": "VP0",
        "paper_center": [200.0, 150.0],
        "paper_size": [300.0, 200.0],
        "view_center": [50.0, 25.0],      # <- the old key
        "view_height": 100.0, "scale": 2.0,
    }
    vp = Viewport.from_dict(legacy)
    assert (vp.view_anchor_x, vp.view_anchor_y) == (50.0, 25.0)
    # and it projects identically to one built from the new key
    modern = dict(legacy)
    del modern["view_center"]
    modern["view_anchor"] = [50.0, 25.0]
    assert Viewport.from_dict(modern).to_paper(0.0, 0.0) == vp.to_paper(0.0, 0.0)


def test_view_anchor_wins_when_both_keys_are_present():
    vp = Viewport.from_dict({
        "index": 0, "handle": "VP0",
        "paper_center": [0.0, 0.0], "paper_size": [10.0, 10.0],
        "view_anchor": [7.0, 8.0], "view_center": [1.0, 2.0],
        "view_height": 10.0, "scale": 1.0,
    })
    assert (vp.view_anchor_x, vp.view_anchor_y) == (7.0, 8.0)


def test_round_trip_through_to_dict_preserves_the_anchor():
    original = _transform().viewports[0]
    assert Viewport.from_dict(original.to_dict()) == original


def test_a_views_own_origin_lands_at_its_paper_centre():
    """iCAD SX draws one ORIGIN marker per view. This is where each one goes.

    It falls out of the algebra -- to_paper(anchor) == paper_center -- but it is the
    question the marker answers, so it is pinned rather than left implicit.
    """
    vp = _transform().viewports[0]
    assert vp.origin_paper_point == (vp.paper_center_x, vp.paper_center_y)


def test_the_global_origin_is_not_the_views_origin():
    """A view's own origin and the global model origin are different points."""
    vp = _transform().viewports[0]          # anchor (50, 25), scale 2, paper centre (200,150)
    assert vp.origin_paper_point == (200.0, 150.0)
    assert vp.to_paper(0.0, 0.0) == (100.0, 100.0)
    assert vp.contains_paper_point(*vp.origin_paper_point)


def test_a_real_sheets_global_origin_falls_outside_its_own_viewport():
    """Measured, not invented: `M745221N01_FSRS2` viewport `2D2` (the sectA view).

    This is the case that makes the anchor/centre distinction matter rather than being a
    naming preference. The view's own origin sits at its paper centre and is visible; the
    GLOBAL model origin projects ~250 units up the sheet and is clipped away entirely. Read
    the anchor as if it were `view_center_point` -- which is (0,0,0) on all three of this
    sheet's viewports -- and you get the second number while believing it is the first.
    """
    vp = Viewport(
        index=1, handle="2D2",
        paper_center_x=247.0576406882221, paper_center_y=145.5561857223511,
        paper_width=48.37035012358122, paper_height=133.4632218360901,
        view_anchor_x=-80.6906589897892, view_anchor_y=-351.47548122406,
        view_height=186.8485105705261, scale=0.7142857142857145,
    )

    own = vp.origin_paper_point
    assert own == (vp.paper_center_x, vp.paper_center_y)
    assert vp.contains_paper_point(*own), "the view's own origin is visible in the view"

    global_origin = vp.to_paper(0.0, 0.0)
    assert math.isclose(global_origin[0], 304.694, abs_tol=1e-3)
    assert math.isclose(global_origin[1], 396.610, abs_tol=1e-3)
    assert not vp.contains_paper_point(*global_origin), "and the global one is clipped away"
