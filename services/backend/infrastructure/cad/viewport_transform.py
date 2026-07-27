"""Invertible model-space <-> paper-space projection for DXF paper-space viewports.

A DXF that draws in model space but plots through a paper-space layout shows its
geometry through one or more VIEWPORT entities. Each viewport is a window: it maps
a rectangular region of model space onto a rectangle of the printed sheet.

The extraction pipeline stores geometry in *paper* coordinates so that everything
(title block, notes, and the projected model views) shares one coordinate system --
the same one the PNG renderer's `render_bounds` describes.

Previously that projection was applied inline in `dxf_parser.py` with the per-entity
scale factor computed and then discarded, so the mapping was one-way. Writing
annotations or redlines back into the source DXF requires the inverse, so the
transform is now an explicit object that is persisted onto the DrawingDocument and
can round-trip a point in either direction.

Guarantees:
  * `unproject(*project(x, y))` returns the original point (within float epsilon)
    for every viewport, including the identity case where a drawing has no
    paper-space viewports at all.
  * Round-tripping is exact only when the viewport index is carried along, because
    overlapping viewports make the point->viewport choice ambiguous. Callers that
    care (i.e. anything persisting a coordinate) should store the returned
    `viewport_index` alongside the point and pass it back on the way out.
"""

from dataclasses import dataclass
from typing import Any

from ...logger import logger

# Bump when the projection maths or the persisted dict shape changes in a way
# that makes previously-extracted coordinates unreadable.
TRANSFORM_VERSION = 1

# Sentinel used when no viewport applies (identity projection).
NO_VIEWPORT = -1


@dataclass(frozen=True)
class Viewport:
    """One paper-space VIEWPORT: a model-space window painted onto the sheet."""

    index: int
    handle: str
    paper_center_x: float
    paper_center_y: float
    paper_width: float
    paper_height: float
    view_center_x: float
    view_center_y: float
    view_height: float
    scale: float

    @property
    def model_half_width(self) -> float:
        return (self.paper_width / self.scale) * 0.5 if self.scale else 0.0

    @property
    def model_half_height(self) -> float:
        return self.view_height * 0.5

    def contains_model_point(self, x: float, y: float) -> bool:
        return (
            self.view_center_x - self.model_half_width <= x <= self.view_center_x + self.model_half_width
            and self.view_center_y - self.model_half_height <= y <= self.view_center_y + self.model_half_height
        )

    def contains_paper_point(self, px: float, py: float) -> bool:
        return (
            self.paper_center_x - self.paper_width * 0.5 <= px <= self.paper_center_x + self.paper_width * 0.5
            and self.paper_center_y - self.paper_height * 0.5 <= py <= self.paper_center_y + self.paper_height * 0.5
        )

    def to_paper(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.paper_center_x + (x - self.view_center_x) * self.scale,
            self.paper_center_y + (y - self.view_center_y) * self.scale,
        )

    def to_model(self, px: float, py: float) -> tuple[float, float]:
        if not self.scale:
            return px, py
        return (
            self.view_center_x + (px - self.paper_center_x) / self.scale,
            self.view_center_y + (py - self.paper_center_y) / self.scale,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "handle": self.handle,
            "paper_center": [self.paper_center_x, self.paper_center_y],
            "paper_size": [self.paper_width, self.paper_height],
            "view_center": [self.view_center_x, self.view_center_y],
            "view_height": self.view_height,
            "scale": self.scale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Viewport":
        pc = data.get("paper_center") or [0.0, 0.0]
        ps = data.get("paper_size") or [0.0, 0.0]
        vc = data.get("view_center") or [0.0, 0.0]
        return cls(
            index=int(data.get("index", NO_VIEWPORT)),
            handle=str(data.get("handle", "")),
            paper_center_x=float(pc[0]),
            paper_center_y=float(pc[1]),
            paper_width=float(ps[0]),
            paper_height=float(ps[1]),
            view_center_x=float(vc[0]),
            view_center_y=float(vc[1]),
            view_height=float(data.get("view_height", 0.0)),
            scale=float(data.get("scale", 1.0)),
        )

    @classmethod
    def from_entity(cls, vp: Any, index: int) -> "Viewport | None":
        """Build from an ezdxf VIEWPORT entity, or None if it is unusable."""
        try:
            center = vp.dxf.center
            width = float(vp.dxf.width)
            height = float(vp.dxf.height)

            # A viewport's model-space look-at lives in view_target_point on most
            # files, but some CAD exporters only populate view_center_point. Prefer
            # the former and fall back when it is absent or a degenerate origin.
            vc = vp.dxf.get("view_target_point")
            if not vc or (vc.x == 0.0 and vc.y == 0.0):
                vc = vp.dxf.get("view_center_point")
            vc_x, vc_y = (float(vc.x), float(vc.y)) if vc else (0.0, 0.0)

            view_height = float(vp.dxf.get("view_height") or 0.0)
            scale = height / view_height if view_height > 0 else 1.0

            return cls(
                index=index,
                handle=str(getattr(vp.dxf, "handle", "") or ""),
                paper_center_x=float(center.x),
                paper_center_y=float(center.y),
                paper_width=width,
                paper_height=height,
                view_center_x=vc_x,
                view_center_y=vc_y,
                view_height=view_height,
                scale=scale,
            )
        except Exception as exc:
            logger.debug(f"Skipping unreadable VIEWPORT at index {index}: {exc}")
            return None


@dataclass(frozen=True)
class Projection:
    """Result of projecting or unprojecting a point."""

    x: float
    y: float
    scale: float
    viewport_index: int


class ViewportTransform:
    """Model <-> paper projection for one paper-space layout.

    With no viewports this is the identity transform, which keeps callers free of
    `if viewports:` branching -- a drawing authored entirely in paper space, or
    entirely in model space with no layout, simply projects to itself at scale 1.
    """

    def __init__(self, layout_name: str | None = None, viewports: list[Viewport] | None = None):
        self.layout_name = layout_name
        self.viewports = viewports or []

    @property
    def is_identity(self) -> bool:
        return not self.viewports

    @classmethod
    def from_document(cls, doc: Any) -> "ViewportTransform":
        """Discover the active paper-space layout and its viewports from an ezdxf doc.

        Picks the first non-empty paper-space layout that owns at least one real
        viewport. VIEWPORT id 1 is the layout's own "paper" pseudo-viewport rather
        than a window onto model space, so it is excluded.
        """
        try:
            paperspace_layouts = [l for l in doc.layouts if l.name.lower() != "model" and len(l) > 0]
        except Exception as exc:
            logger.warning(f"Could not enumerate layouts; using identity transform: {exc}")
            return cls()

        for layout in paperspace_layouts:
            try:
                candidates = [e for e in layout if e.dxftype() == "VIEWPORT" and e.dxf.id != 1]
            except Exception:
                continue
            if not candidates:
                continue
            viewports = []
            for i, vp in enumerate(candidates):
                built = Viewport.from_entity(vp, i)
                if built is not None:
                    viewports.append(built)
            if viewports:
                logger.info(
                    f"Viewport transform resolved on layout '{layout.name}' "
                    f"with {len(viewports)} viewport(s)."
                )
                return cls(layout_name=layout.name, viewports=viewports)

        return cls()

    def _resolve(self, index: int | None) -> Viewport | None:
        if index is None or index == NO_VIEWPORT:
            return None
        for vp in self.viewports:
            if vp.index == index:
                return vp
        return None

    def project(self, x: float, y: float, viewport_index: int | None = None) -> Projection:
        """Model space -> paper space."""
        if self.is_identity:
            return Projection(x, y, 1.0, NO_VIEWPORT)

        pinned = self._resolve(viewport_index)
        if pinned is not None:
            px, py = pinned.to_paper(x, y)
            return Projection(px, py, pinned.scale, pinned.index)

        for vp in self.viewports:
            if vp.contains_model_point(x, y):
                px, py = vp.to_paper(x, y)
                return Projection(px, py, vp.scale, vp.index)

        # Geometry outside every viewport window still has to land somewhere
        # deterministic -- fall back to the first viewport rather than dropping it.
        vp = self.viewports[0]
        px, py = vp.to_paper(x, y)
        return Projection(px, py, vp.scale, vp.index)

    def unproject(self, px: float, py: float, viewport_index: int | None = None) -> Projection:
        """Paper space -> model space. Exact inverse of `project` for the same viewport.

        Note the deliberate asymmetry with `project`, which falls back to the first
        viewport for model geometry outside every window: that geometry has to be drawn
        *somewhere*, so a deterministic choice beats dropping it.

        Unprojection has no such obligation. A paper point outside every viewport rect
        is not "in viewport 0" -- it is on the sheet itself, marking a title-block field
        or a note. Returning it unchanged with NO_VIEWPORT reports that truthfully, and
        callers depend on the distinction: `coordinate_stamp` uses it to record where a
        point was authored, and `redline_writer` uses it to decide whether a finding
        belongs in model space or on the sheet. Falling back here would silently claim
        every title-block annotation lived inside a viewport.
        """
        if self.is_identity:
            return Projection(px, py, 1.0, NO_VIEWPORT)

        pinned = self._resolve(viewport_index)
        if pinned is not None:
            x, y = pinned.to_model(px, py)
            return Projection(x, y, pinned.scale, pinned.index)

        for vp in self.viewports:
            if vp.contains_paper_point(px, py):
                x, y = vp.to_model(px, py)
                return Projection(x, y, vp.scale, vp.index)

        return Projection(px, py, 1.0, NO_VIEWPORT)

    def scale_for(self, viewport_index: int | None) -> float:
        vp = self._resolve(viewport_index)
        return vp.scale if vp is not None else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": TRANSFORM_VERSION,
            "layout": self.layout_name,
            "viewports": [vp.to_dict() for vp in self.viewports],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ViewportTransform":
        if not data:
            return cls()
        version = data.get("version")
        if version != TRANSFORM_VERSION:
            logger.warning(
                f"Viewport transform version mismatch (stored={version}, "
                f"expected={TRANSFORM_VERSION}); treating as identity."
            )
            return cls()
        viewports = [Viewport.from_dict(v) for v in (data.get("viewports") or [])]
        return cls(layout_name=data.get("layout"), viewports=viewports)
