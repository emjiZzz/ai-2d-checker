"""Stamps provenance onto incoming coordinates, and detects when it has gone stale.

Clients send bare `[x, y]` pairs. The server -- which owns the DrawingDocument and
therefore knows the coordinate space, layout, transform version and render bounds --
fills the rest in. Doing it here rather than trusting the client means a coordinate's
provenance cannot disagree with the drawing it is attached to, and callers do not
have to be taught about coordinate spaces to store a correct point.
"""

from typing import Any

from ...domain.models.cad_point import CadPoint
from ...logger import logger
from .viewport_transform import NO_VIEWPORT, ViewportTransform

# Render bounds are floats derived from a matplotlib autoscale; compare with a
# tolerance rather than for exact equality.
BOUNDS_EPSILON = 1e-6


def _drawing_metadata(drawing: Any) -> dict[str, Any]:
    return (getattr(drawing, "metadata", None) or {}) if drawing is not None else {}


def stamp_cad_point(x: float, y: float, drawing: Any) -> CadPoint:
    """Build a fully-described CadPoint for a raw coordinate on `drawing`.

    `viewport_index` is resolved by asking the drawing's own viewport transform which
    viewport's paper rect contains the point. That is what later lets the point be
    inverted back into model space for CAD writeback -- with overlapping viewports the
    mapping is ambiguous unless the index is recorded at authoring time.
    """
    metadata = _drawing_metadata(drawing)
    transform_data = metadata.get("viewport_transform") or {}
    raw_bounds = metadata.get("render_bounds")

    # Absent coordinate_space means no CAD transform describes this drawing -- the PDF
    # ingestion path measures against the PyMuPDF page rect, which is neither model nor
    # paper space.
    space = metadata.get("coordinate_space") or "render"
    if space not in ("model", "paper", "render"):
        logger.warning(f"Unrecognised coordinate_space '{space}' on drawing; treating as 'render'.")
        space = "render"

    viewport_index = NO_VIEWPORT
    if transform_data:
        try:
            transform = ViewportTransform.from_dict(transform_data)
            if not transform.is_identity:
                viewport_index = transform.unproject(x, y).viewport_index
        except Exception as exc:
            logger.debug(f"Could not resolve viewport index while stamping point: {exc}")

    bounds = None
    if isinstance(raw_bounds, (list, tuple)) and len(raw_bounds) >= 4:
        bounds = [float(v) for v in raw_bounds[:4]]

    return CadPoint(
        x=float(x),
        y=float(y),
        space=space,
        layout=transform_data.get("layout"),
        viewport_index=viewport_index,
        transform_version=int(metadata.get("transform_version", 0) or 0),
        bounds=bounds,
    )


def stamp_pair(pair: Any, drawing: Any) -> CadPoint | None:
    """Stamp a raw `[x, y]` (or an already-stamped CadPoint) against `drawing`."""
    if pair is None:
        return None
    if isinstance(pair, CadPoint):
        return pair
    if isinstance(pair, dict):
        # Already an envelope from a client that knows the shape.
        try:
            return CadPoint(**pair)
        except Exception:
            return None
    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
        try:
            return stamp_cad_point(float(pair[0]), float(pair[1]), drawing)
        except (TypeError, ValueError):
            return None
    return None


def has_drifted(point: CadPoint | None, drawing: Any) -> bool:
    """True when a stored point's render bounds no longer match the drawing's.

    A True here means the drawing was re-rendered against different bounds since the
    point was authored, so its on-screen position is no longer trustworthy. Previously
    this was undetectable -- the pin simply moved and nothing recorded it.
    """
    if point is None or point.bounds is None:
        return False

    current = _drawing_metadata(drawing).get("render_bounds")
    if not isinstance(current, (list, tuple)) or len(current) < 4:
        return False

    try:
        return any(
            abs(float(current[i]) - float(point.bounds[i])) > BOUNDS_EPSILON
            for i in range(4)
        )
    except (TypeError, ValueError):
        return False
