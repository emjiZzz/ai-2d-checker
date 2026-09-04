"""Phase 5: writing audit findings back into a DXF as a redline layer.

The central guarantee under test is that the source drawing is *added to*, never
rebuilt: the output must be a strict superset of the input, so everything the
extraction pipeline does not capture survives untouched. That is what makes writeback
depend on the viewport transform alone rather than on entity-model fidelity.

DXF output only -- DWG export would put the ODA converter on the write path and is not
currently required.
"""

import math
from pathlib import Path

import ezdxf
import pytest

from services.backend.domain.models.cad_point import CadPoint
from services.backend.infrastructure.cad.coordinate_stamp import stamp_cad_point
from services.backend.infrastructure.cad.dxf_parser import DXFParser
from services.backend.infrastructure.cad.redline_writer import (
    RedlineWriter,
    build_findings,
    redline_layer_name,
)
from services.backend.infrastructure.cad.viewport_transform import (
    NO_VIEWPORT,
    Viewport,
    ViewportTransform,
)
from services.backend.infrastructure.storage.path_resolver import bootstrap_storage, get_storage_root

EPSILON = 1e-6


@pytest.fixture(scope="module", autouse=True)
def setup_storage():
    bootstrap_storage()
    yield


@pytest.fixture
def sandbox(request) -> Path:
    """A scratch directory inside the storage root.

    `DXFParser.parse_file` enforces the sandbox via `validate_sandboxed_path`, so
    pytest's `tmp_path` is rejected outright -- fixtures and outputs both have to live
    under `storage/`. Files are namespaced per test and removed afterwards.
    """
    root = get_storage_root() / "temp" / f"phase5_{request.node.name[:40]}"
    root.mkdir(parents=True, exist_ok=True)
    yield root
    for child in root.glob("*"):
        try:
            child.unlink()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


class FakeDrawing:
    def __init__(self, metadata):
        self.metadata = metadata


@pytest.fixture
def viewport_dxf(sandbox) -> Path:
    """A drawing plotted through a paper-space viewport, plus sheet-native content."""
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 50))
    msp.add_circle((50, 25), radius=10)
    doc.layers.add("EXISTING_LAYER", color=5)

    layout = doc.layout("Layout1")
    layout.add_viewport(
        center=(200, 150), size=(300, 200), view_center_point=(50, 25), view_height=100
    )
    layout.add_text("TITLE BLOCK", dxfattribs={"insert": (20, 20), "height": 5})

    path = sandbox / "viewport.dxf"
    doc.saveas(str(path))
    return path


@pytest.fixture
def model_only_dxf(sandbox) -> Path:
    """A drawing with no paper space at all -- the identity-transform case."""
    doc = ezdxf.new("R2018", setup=True)
    doc.modelspace().add_line((0, 0), (100, 100))
    path = sandbox / "model_only.dxf"
    doc.saveas(str(path))
    return path


def _transform_for(path: Path) -> tuple[ViewportTransform, dict]:
    _, _, _, metadata = DXFParser().parse_file(path)
    return ViewportTransform.from_dict(metadata.get("viewport_transform")), metadata


def _handles(path: Path) -> set[str]:
    doc = ezdxf.readfile(str(path), encoding="latin-1")
    return {e.dxf.handle for layout in doc.layouts for e in layout if e.dxf.hasattr("handle")}


def _cloud_centroids(space, layer: str) -> list[tuple[float, float]]:
    centroids = []
    for entity in space:
        if entity.dxftype() != "LWPOLYLINE" or entity.dxf.layer != layer:
            continue
        pts = list(entity.get_points(format="xy"))
        if len(pts) >= 8:  # a cloud, not the 3-point leader
            centroids.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
    return centroids


# --------------------------------------------------------------------------
# The central guarantee: add a layer, never rebuild
# --------------------------------------------------------------------------

def test_output_is_a_superset_of_the_source(viewport_dxf, sandbox):
    """Every original entity must survive. This is why redline export does not depend
    on the fidelity of the extracted entity model -- the original is never rebuilt
    from it."""
    transform, _ = _transform_for(viewport_dxf)
    point = CadPoint(x=250.0, y=150.0, space="paper", viewport_index=0)
    out = sandbox / "redline.dxf"

    RedlineWriter(viewport_dxf, transform).write(
        [{"point": point, "text": "finding", "severity": "high"}], "sess1", out
    )

    before, after = _handles(viewport_dxf), _handles(out)
    assert not (before - after), f"lost {len(before - after)} original entities"


def test_original_file_is_not_modified(viewport_dxf, sandbox):
    original_bytes = viewport_dxf.read_bytes()
    transform, _ = _transform_for(viewport_dxf)
    RedlineWriter(viewport_dxf, transform).write(
        [{"point": CadPoint(x=250.0, y=150.0, viewport_index=0), "text": "x", "severity": "low"}],
        "sess1",
        sandbox / "redline.dxf",
    )
    assert viewport_dxf.read_bytes() == original_bytes


def test_exactly_one_layer_is_added(viewport_dxf, sandbox):
    transform, _ = _transform_for(viewport_dxf)
    out = sandbox / "redline.dxf"
    RedlineWriter(viewport_dxf, transform).write(
        [{"point": CadPoint(x=250.0, y=150.0, viewport_index=0), "text": "x", "severity": "low"}],
        "sess1",
        out,
    )

    before = {l.dxf.name for l in ezdxf.readfile(str(viewport_dxf), encoding="latin-1").layers}
    after = {l.dxf.name for l in ezdxf.readfile(str(out), encoding="latin-1").layers}
    assert not (before - after), "an existing layer was removed"
    assert after - before == {redline_layer_name("sess1")}


# --------------------------------------------------------------------------
# Space routing: a finding is written where it actually belongs
# --------------------------------------------------------------------------

def test_sheet_native_finding_goes_to_paper_space(viewport_dxf, sandbox):
    """A point outside every viewport rect marks the sheet itself -- a title-block
    field or a note -- so it stays on the sheet at the coordinates the reviewer used."""
    transform, metadata = _transform_for(viewport_dxf)
    point = stamp_cad_point(20.0, 20.0, FakeDrawing(metadata))
    assert point.viewport_index == NO_VIEWPORT, "fixture point is not sheet-native"

    out = sandbox / "redline.dxf"
    summary = RedlineWriter(viewport_dxf, transform).write(
        [{"point": point, "text": "title block", "severity": "high"}], "sess1", out
    )
    assert summary["placed_paper_space"] == 1
    assert summary["placed_model_space"] == 0

    doc = ezdxf.readfile(str(out), encoding="latin-1")
    centroids = _cloud_centroids(doc.layout(transform.layout_name), redline_layer_name("sess1"))
    assert len(centroids) == 1
    assert math.isclose(centroids[0][0], 20.0, abs_tol=1e-6)
    assert math.isclose(centroids[0][1], 20.0, abs_tol=1e-6)


def test_in_view_finding_is_inverted_into_model_space(viewport_dxf, sandbox):
    """A point inside a viewport marks model geometry, so the redline goes into model
    space and stays attached to what it annotates rather than floating on the sheet."""
    transform, metadata = _transform_for(viewport_dxf)
    point = stamp_cad_point(250.0, 150.0, FakeDrawing(metadata))
    assert point.viewport_index >= 0, "fixture point is not inside a viewport"

    out = sandbox / "redline.dxf"
    summary = RedlineWriter(viewport_dxf, transform).write(
        [{"point": point, "text": "geometry", "severity": "critical"}], "sess1", out
    )
    assert summary["placed_model_space"] == 1
    assert summary["placed_paper_space"] == 0

    doc = ezdxf.readfile(str(out), encoding="latin-1")
    centroids = _cloud_centroids(doc.modelspace(), redline_layer_name("sess1"))
    assert len(centroids) == 1

    # Re-projecting through the same viewport must return the authored paper position.
    reprojected = transform.project(centroids[0][0], centroids[0][1], point.viewport_index)
    assert math.isclose(reprojected.x, 250.0, abs_tol=1e-6)
    assert math.isclose(reprojected.y, 150.0, abs_tol=1e-6)


def test_identity_transform_writes_to_model_space(model_only_dxf, sandbox):
    transform, metadata = _transform_for(model_only_dxf)
    assert transform.is_identity

    point = stamp_cad_point(40.0, 40.0, FakeDrawing(metadata))
    out = sandbox / "redline.dxf"
    summary = RedlineWriter(model_only_dxf, transform).write(
        [{"point": point, "text": "finding", "severity": "medium"}], "sess1", out
    )
    assert summary["placed_model_space"] == 1

    doc = ezdxf.readfile(str(out), encoding="latin-1")
    centroids = _cloud_centroids(doc.modelspace(), redline_layer_name("sess1"))
    assert math.isclose(centroids[0][0], 40.0, abs_tol=1e-6)
    assert math.isclose(centroids[0][1], 40.0, abs_tol=1e-6)


def test_unproject_reports_sheet_native_points_honestly():
    """Regression guard. `unproject` used to fall back to viewport 0 when no viewport
    contained the point, which claimed every title-block annotation lived inside a
    viewport and routed its redline into model space. `project` keeps its fallback --
    geometry outside every window still has to be drawn somewhere -- but unprojection
    has no such obligation."""
    vp = Viewport(
        index=0, handle="VP0",
        paper_center_x=200.0, paper_center_y=150.0,
        paper_width=300.0, paper_height=200.0,
        view_anchor_x=50.0, view_anchor_y=25.0,
        view_height=100.0, scale=2.0,
    )
    transform = ViewportTransform("Layout1", [vp])

    outside = transform.unproject(5.0, 5.0)
    assert outside.viewport_index == NO_VIEWPORT
    assert (outside.x, outside.y) == (5.0, 5.0), "a sheet point must pass through unchanged"

    inside = transform.unproject(250.0, 150.0)
    assert inside.viewport_index == 0

    # Pinning still forces the transform, which is what round-tripping relies on.
    pinned = transform.unproject(5.0, 5.0, viewport_index=0)
    assert pinned.viewport_index == 0
    assert (pinned.x, pinned.y) != (5.0, 5.0)


# --------------------------------------------------------------------------
# Re-ingestion through the system's own pipeline
# --------------------------------------------------------------------------

def test_redline_survives_reingestion(viewport_dxf, sandbox):
    transform, metadata = _transform_for(viewport_dxf)
    point = stamp_cad_point(250.0, 150.0, FakeDrawing(metadata))
    out = sandbox / "redline.dxf"
    RedlineWriter(viewport_dxf, transform).write(
        [{"point": point, "text": "finding", "severity": "high"}], "sess1", out
    )

    entities, _, _, _ = DXFParser().parse_file(out)
    layer = redline_layer_name("sess1")
    redlines = [e for e in entities if e["layer"] == layer]
    assert redlines, "redline layer did not survive re-ingestion"

    clouds = [
        e for e in redlines
        if e["entity_type"] == "polyline" and len(e["geometry"].get("points", [])) >= 8
    ]
    assert clouds, "no revision cloud found after re-ingestion"

    pts = clouds[0]["geometry"]["points"]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    # Re-ingestion re-projects model geometry into paper space, landing back where the
    # finding was authored.
    assert math.hypot(cx - 250.0, cy - 150.0) < 1.0


# --------------------------------------------------------------------------
# Finding assembly and edge cases
# --------------------------------------------------------------------------

class FakeViolation:
    def __init__(self, coordinates, severity="high", description="a violation"):
        self.coordinates = coordinates
        self.severity = severity
        self.description = description


class FakeAnnotation:
    def __init__(self, coordinates, severity="info", content="a note"):
        self.coordinates = coordinates
        self.severity = severity
        self.content = content


def test_build_findings_expands_multi_point_violations():
    """layer_rules emits a start/end pair on one violation; each must become its own
    marker rather than only the first being drawn."""
    violation = FakeViolation([CadPoint(x=1.0, y=2.0), CadPoint(x=3.0, y=4.0)])
    findings = build_findings([violation])
    assert len(findings) == 2
    assert all(f["severity"] == "high" for f in findings)


def test_build_findings_includes_annotations():
    findings = build_findings([], [FakeAnnotation(CadPoint(x=5.0, y=6.0), content="check me")])
    assert len(findings) == 1
    assert findings[0]["text"] == "check me"


def test_build_findings_skips_missing_coordinates():
    assert build_findings([FakeViolation(None)], [FakeAnnotation(None)]) == []
    assert build_findings([], []) == []


def test_findings_without_a_point_are_reported_not_dropped_silently(viewport_dxf, sandbox):
    transform, _ = _transform_for(viewport_dxf)
    out = sandbox / "redline.dxf"
    summary = RedlineWriter(viewport_dxf, transform).write(
        [{"point": None, "text": "unplaceable", "severity": "low"}], "sess1", out
    )
    assert summary["total"] == 0
    assert summary["skipped"] == ["unplaceable"]


def test_layer_name_is_dxf_safe():
    assert redline_layer_name("abc123") == "AI_REDLINE_abc123"
    # DXF forbids these characters in a layer name.
    assert "/" not in redline_layer_name("a/b")
    assert "*" not in redline_layer_name("a*b")
    assert len(redline_layer_name("x" * 400)) <= 255


def test_missing_source_file_raises(tmp_path):
    writer = RedlineWriter(tmp_path / "nope.dxf", ViewportTransform())
    with pytest.raises(FileNotFoundError):
        writer.write([], "sess1", tmp_path / "out.dxf")


def test_severity_drives_redline_colour(viewport_dxf, sandbox):
    transform, _ = _transform_for(viewport_dxf)
    out = sandbox / "redline.dxf"
    RedlineWriter(viewport_dxf, transform).write(
        [
            {"point": CadPoint(x=250.0, y=150.0, viewport_index=0), "text": "c", "severity": "critical"},
            {"point": CadPoint(x=260.0, y=160.0, viewport_index=0), "text": "l", "severity": "low"},
        ],
        "sess1",
        out,
    )
    doc = ezdxf.readfile(str(out), encoding="latin-1")
    layer = redline_layer_name("sess1")
    colours = {e.dxf.color for e in doc.modelspace() if e.dxf.layer == layer}
    assert 1 in colours, "critical should be red"
    assert 3 in colours, "low should be green"
