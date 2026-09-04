"""Writes audit findings back into a DXF as a redline layer.

The whole design rests on one property: the original drawing is never rebuilt.
The source file is opened, one new layer is added, and the result is saved to a new
path. Everything the extraction pipeline does not capture -- lineweights it never read,
hatch patterns, dimension styles, xrefs, proprietary objects, the entire header -- is
preserved because it is never touched. That is why redline export depends on the
viewport transform alone and not on the fidelity of the entity model.

## Which space a redline is written into

A finding's coordinate carries a `viewport_index` recorded when it was stamped (see
`coordinate_stamp.py`), and that is exactly the discriminator needed:

  * No viewport transform at all -- the drawing is model-space only. Coordinates are
    already model-space; write to model space.
  * `viewport_index == -1` -- the point sits outside every viewport rect, so it marks
    something native to the sheet: a title-block field, a note, a BOM cell. Write it to
    the paper-space layout at the stored coordinates, where the reviewer put it.
  * `viewport_index >= 0` -- the point sits inside a viewport, so it marks model
    geometry seen through that window. Invert it back into model space and write it
    there, so the redline stays attached to the geometry it annotates rather than
    floating on the sheet.

Writing everything to one space would be simpler and wrong in one direction or the
other: sheet-space markup would drift away from geometry, or geometry markup would be
stranded on the sheet.

DXF output only. DWG export would need the ODA converter on the write path and is not
currently required.
"""

import math
import re
from pathlib import Path
from typing import Any

import ezdxf

from ...domain.models.cad_point import CadPoint
from ...logger import logger
from .viewport_transform import NO_VIEWPORT, ViewportTransform

# AutoCAD Color Index per severity. Redlines are conventionally warm/red; green is
# reserved for resolved items so a cleared finding reads differently at a glance.
SEVERITY_COLOR = {
    "critical": 1,   # red
    "high": 1,       # red
    "medium": 2,     # yellow
    "low": 3,        # green
}
DEFAULT_COLOR = 1

# Revision-cloud geometry. A closed LWPOLYLINE whose segments bulge outward is the
# standard way to draw one; bulge = tan(theta/4) for an arc of included angle theta.
CLOUD_SEGMENTS = 12
CLOUD_BULGE = 0.45

# Marker and text sizing, as a fraction of the drawing's diagonal, so a redline reads
# the same on an A4 detail and an A0 assembly.
CLOUD_RADIUS_FRACTION = 0.012
TEXT_HEIGHT_FRACTION = 0.008
LEADER_LENGTH_FRACTION = 0.045

# DXF forbids these in a layer name.
_INVALID_LAYER_CHARS = re.compile(r'[<>/\\":;?*|,=`]')


def redline_layer_name(session_id: str) -> str:
    """Layer name for a session's redlines, safe for DXF."""
    cleaned = _INVALID_LAYER_CHARS.sub("_", str(session_id))
    return f"AI_REDLINE_{cleaned}"[:255]


def _revision_cloud_points(cx: float, cy: float, radius: float) -> list[tuple[float, float, float, float, float]]:
    """LWPOLYLINE vertices (x, y, start_width, end_width, bulge) forming a scalloped cloud."""
    points = []
    for i in range(CLOUD_SEGMENTS):
        angle = 2 * math.pi * i / CLOUD_SEGMENTS
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), 0.0, 0.0, CLOUD_BULGE))
    return points


def _drawing_scale_reference(doc: Any, layout_name: str | None) -> float:
    """A characteristic size for the sheet, used to scale markers and text.

    Falls back through header extents, then the target layout's own extents, then a
    conservative default -- a redline sized off a wrong reference is still visible,
    but one sized off zero is not.
    """
    try:
        extmin = doc.header.get("$EXTMIN", None)
        extmax = doc.header.get("$EXTMAX", None)
        if extmin and extmax:
            diagonal = math.hypot(float(extmax[0]) - float(extmin[0]), float(extmax[1]) - float(extmin[1]))
            if 0 < diagonal < 1e9:
                return diagonal
    except Exception:
        pass

    try:
        from ezdxf import bbox
        layout = doc.layout(layout_name) if layout_name else doc.modelspace()
        box = bbox.extents(layout)
        diagonal = math.hypot(box.extmax.x - box.extmin.x, box.extmax.y - box.extmin.y)
        if 0 < diagonal < 1e9:
            return diagonal
    except Exception:
        pass

    logger.warning("Could not determine drawing extents for redline sizing; using A3 default.")
    return 500.0


class RedlineWriter:
    """Adds an audit session's findings to a copy of the source DXF."""

    def __init__(self, source_dxf: Path, transform: ViewportTransform):
        self.source_dxf = Path(source_dxf)
        self.transform = transform

    def _resolve_target(self, point: CadPoint) -> tuple[str | None, float, float]:
        """Decide which space this point belongs in, and its coordinates there.

        Returns (layout_name_or_None_for_modelspace, x, y). See the module docstring.
        """
        if self.transform.is_identity:
            return None, point.x, point.y

        if point.viewport_index == NO_VIEWPORT:
            # Native to the sheet -- keep it on the sheet.
            return self.transform.layout_name, point.x, point.y

        # Seen through a viewport: put it back on the geometry it annotates.
        model = self.transform.unproject(point.x, point.y, point.viewport_index)
        return None, model.x, model.y

    def write(
        self,
        findings: list[dict[str, Any]],
        session_id: str,
        output_path: Path,
    ) -> dict[str, Any]:
        """Write `findings` into a copy of the source DXF at `output_path`.

        Each finding is `{point: CadPoint, text: str, severity: str}`. Returns a summary
        including per-space counts and any findings that could not be placed.
        """
        if not self.source_dxf.exists():
            raise FileNotFoundError(f"Source DXF not found for redline export: {self.source_dxf}")

        # latin-1 preserves the raw CJK bytes on read so they survive the round trip
        # untouched -- the same reason dxf_parser opens files this way.
        doc = ezdxf.readfile(str(self.source_dxf), encoding="latin-1")

        layer_name = redline_layer_name(session_id)
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=DEFAULT_COLOR)

        scale_ref = _drawing_scale_reference(doc, self.transform.layout_name)
        cloud_radius = scale_ref * CLOUD_RADIUS_FRACTION
        text_height = scale_ref * TEXT_HEIGHT_FRACTION
        leader_length = scale_ref * LEADER_LENGTH_FRACTION

        placed = {"model": 0, "paper": 0}
        skipped: list[str] = []

        for finding in findings:
            point = finding.get("point")
            if not isinstance(point, CadPoint):
                skipped.append(finding.get("text", "<no text>"))
                continue

            layout_name, x, y = self._resolve_target(point)
            try:
                target = doc.modelspace() if layout_name is None else doc.layout(layout_name)
            except Exception as exc:
                logger.warning(f"Redline layout '{layout_name}' unavailable ({exc}); falling back to model space.")
                target = doc.modelspace()
                layout_name = None

            color = SEVERITY_COLOR.get(str(finding.get("severity", "")).lower(), DEFAULT_COLOR)
            attribs = {"layer": layer_name, "color": color}

            target.add_lwpolyline(
                _revision_cloud_points(x, y, cloud_radius),
                format="xyseb",
                close=True,
                dxfattribs=attribs,
            )

            # Leader out to the upper right, then a short horizontal shoulder the note
            # sits on -- the usual annotation convention, and it keeps the text clear of
            # the geometry being marked.
            elbow_x = x + leader_length
            elbow_y = y + leader_length
            target.add_lwpolyline(
                [(x + cloud_radius * 0.7, y + cloud_radius * 0.7), (elbow_x, elbow_y),
                 (elbow_x + leader_length * 0.4, elbow_y)],
                dxfattribs=attribs,
            )

            text = str(finding.get("text", "")).strip() or "Audit finding"
            mtext = target.add_mtext(text, dxfattribs={**attribs, "char_height": text_height})
            mtext.set_location((elbow_x + leader_length * 0.45, elbow_y + text_height * 0.5))

            placed["paper" if layout_name else "model"] += 1

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(output_path))

        summary = {
            "layer": layer_name,
            "output": str(output_path),
            "placed_model_space": placed["model"],
            "placed_paper_space": placed["paper"],
            "skipped": skipped,
            "total": placed["model"] + placed["paper"],
        }
        logger.info(
            f"Redline DXF written to {output_path.name}: {summary['total']} finding(s) "
            f"({placed['model']} model, {placed['paper']} paper), layer '{layer_name}'."
        )
        return summary


def build_findings(violations: list[Any], annotations: list[Any] | None = None) -> list[dict[str, Any]]:
    """Flatten violations and annotations into the writer's finding shape.

    A violation may carry several coordinates (`layer_rules` emits a start/end pair);
    each becomes its own marker so nothing is silently dropped.
    """
    findings: list[dict[str, Any]] = []

    for violation in violations or []:
        points = getattr(violation, "coordinates", None) or []
        severity = getattr(violation, "severity", "medium")
        description = getattr(violation, "description", "") or ""
        for point in points:
            if isinstance(point, CadPoint):
                findings.append({"point": point, "text": description, "severity": severity})

    for annotation in annotations or []:
        point = getattr(annotation, "coordinates", None)
        if isinstance(point, CadPoint):
            findings.append({
                "point": point,
                "text": getattr(annotation, "content", "") or "",
                "severity": getattr(annotation, "severity", "info"),
            })

    return findings
