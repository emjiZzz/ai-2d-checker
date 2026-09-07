"""CadPoint — a coordinate that knows which space it lives in.

Persisted coordinates used to be bare `[x, y]` arrays with no units, no layout, and
no snapshot of the render bounds they were authored against. That made a class of
silent corruption possible: if a drawing was re-rendered and a different paper-space
layout became the render target, `render_bounds` changed underneath every stored
annotation and each pin moved, with nothing recording that it had happened.

A CadPoint carries its own provenance, so a stored coordinate can be:
  * mapped back into the source file's model space (Phase 5 CAD writeback), using
    `layout` + `viewport_index` against the drawing's persisted viewport transform;
  * checked for drift, by comparing `bounds` against the drawing's current
    render bounds.

Deliberately a plain pydantic model with no imports beyond pydantic: it is shared by
the Beanie documents (domain) and the FastAPI wire schemas (api), so it must not drag
infrastructure in. Stamping lives in `infrastructure/cad/coordinate_stamp.py`.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Where a coordinate's numbers are measured.
#   model  -- the source CAD file's own model space
#   paper  -- a paper-space layout, i.e. model geometry already projected through a
#             VIEWPORT (what DXF drawings with a plotted layout store)
#   render -- the renderer's output space, used when no CAD transform describes it
#             (PDF ingestion measures against the PyMuPDF page rect, top-left origin)
CoordinateSpace = Literal["model", "paper", "render"]


class CadPoint(BaseModel):
    """A 2D coordinate plus the provenance needed to interpret it later."""

    x: float
    y: float
    space: CoordinateSpace = Field(
        "render", description="Which coordinate space x/y are measured in"
    )
    layout: str | None = Field(
        None, description="Paper-space layout name this point was authored against, if any"
    )
    viewport_index: int = Field(
        -1, description="Index into the drawing's viewport transform; -1 for identity/no viewport"
    )
    transform_version: int = Field(
        0, description="Version of the viewport transform maths in force when this point was stamped"
    )
    bounds: list[float] | None = Field(
        None,
        description="Snapshot of the drawing's render_bounds [xmin, ymin, xmax, ymax] at authoring time, for drift detection",
    )

    def as_pair(self) -> list[float]:
        """The bare [x, y] form, for consumers that only need the numbers."""
        return [self.x, self.y]


def coerce_cad_point(value: object) -> "CadPoint | None":
    """Accept a CadPoint, a `{x, y, ...}` dict, or a bare `[x, y]` pair.

    Producers that know the drawing context stamp full provenance up front (see
    `infrastructure/cad/coordinate_stamp.py`). Producers that genuinely do not -- the
    rule engines emit violations from entity geometry alone, with no DrawingDocument in
    scope -- fall through to here and get an honestly under-specified point rather than
    a shape mismatch. `space` then keeps its "render" default, meaning "unqualified".
    """
    if value is None:
        return None
    if isinstance(value, CadPoint):
        return value
    if isinstance(value, dict):
        try:
            return CadPoint(**value)
        except Exception:
            return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return CadPoint(x=float(value[0]), y=float(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def coerce_cad_point_list(value: object) -> "list[CadPoint] | None":
    """Normalise the several shapes callers pass for a set of points.

    Handles `None`, a list of CadPoints/dicts/pairs, and a single bare `[x, y]` --
    which several violation producers pass unwrapped.
    """
    if value is None:
        return None
    if isinstance(value, CadPoint):
        return [value]
    if not isinstance(value, (list, tuple)):
        return None
    if not value:
        return None

    # A single unwrapped [x, y] pair rather than a list of points.
    if all(isinstance(v, (int, float)) for v in value):
        point = coerce_cad_point(value)
        return [point] if point else None

    points = [coerce_cad_point(v) for v in value]
    resolved = [p for p in points if p is not None]
    return resolved or None
