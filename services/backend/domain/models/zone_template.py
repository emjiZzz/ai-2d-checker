from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, IndexModel


# Canonical comparison-zone keys. A template may only pin these. The zones *response* object
# (schemas.py::DrawingZonesResponse) also carries non-zone metadata like "drawing_id" and
# "render_bounds"; if a save path copies that object wholesale those keys leak in and pollute
# the template. Nothing consumes them, but they corrupt the stored set — so upsert strips
# anything outside this whitelist. Mirrors ZONE_KEYS in api/routers/drawings.py and
# apps/desktop/src/services/drawingsApi.ts (order there is render order; membership is all
# that matters here).
VALID_ZONE_KEYS: frozenset[str] = frozenset(
    {"views", "notes", "bom", "title", "tolerance", "iso", "title_upper_left", "shim"}
)


# Below this an outline encloses no area. Mirrors MIN_ZONE_POINTS in
# infrastructure/audit/bom/zone_geometry.py and apps/desktop/src/utils/zoneFractions.ts.
MIN_ZONE_POINTS = 3


class ZonePoint(BaseModel):
    """One vertex of a zone outline, as fractions of render_bounds, Y-DOWN (0 = top).

    Same space and same clamping as ZoneFractions' scalars, so an outline and the box it
    derives cannot end up in different coordinate systems.
    """

    x: float = Field(..., ge=-0.5, le=1.5)
    y: float = Field(..., ge=-0.5, le=1.5)

    @field_validator("x", "y", mode="before")
    @classmethod
    def clamp_bounds(cls, v: float) -> float:
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return v


class ZoneFractions(BaseModel):
    """One zone's position as fractions of the drawing's render_bounds.

    Y-DOWN: yMin 0 is the top of the sheet, matching screen orientation and the client's
    `customRegions` convention. Detected zone boxes are the opposite (CAD, Y-up), and the
    conversion lives in `apps/desktop/src/utils/zoneFractions.ts` — see the module docstring
    there before touching either side.

    Fractions rather than absolute CAD units so one template covers every sheet sharing a
    layout regardless of scale: the corpus this was built against has sheets 1155x817 and
    462x327 units at the same 1.4141 aspect, where absolute coordinates transfer not at all.
    """
    xMin: float = Field(..., ge=-0.5, le=1.5)
    xMax: float = Field(..., ge=-0.5, le=1.5)
    yMin: float = Field(..., ge=-0.5, le=1.5)
    yMax: float = Field(..., ge=-0.5, le=1.5)
    points: Optional[list[ZonePoint]] = Field(
        default=None,
        description=(
            "Polygon outline in the same Y-DOWN fraction space, in draw order. Present only "
            "for a zone the user reshaped by inserting nodes on its edges; the four scalars "
            "above are then this outline's DERIVED bounding box. Absent means the zone is the "
            "rectangle it has always been, so templates written before reshaping existed "
            "parse unchanged and need no migration."
        ),
    )

    @field_validator("xMin", "xMax", "yMin", "yMax", mode="before")
    @classmethod
    def clamp_bounds(cls, v: float) -> float:
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return v

    @field_validator("points")
    @classmethod
    def drop_degenerate_outline(
        cls, points: Optional[list[ZonePoint]]
    ) -> Optional[list[ZonePoint]]:
        """An outline with fewer than 3 vertices encloses nothing.

        Stored as-is it would be a shape that contains no entity at all — a zone that silently
        compares nothing, which is the false-negative direction. Dropped to None instead, which
        degrades the zone to its bounding rectangle: visibly wrong rather than invisibly empty.
        """
        if points is not None and len(points) < MIN_ZONE_POINTS:
            return None
        return points

    def outline(self) -> Optional[list[tuple[float, float]]]:
        """The outline as plain (x, y) pairs, or None for a rectangle."""
        if not self.points or len(self.points) < MIN_ZONE_POINTS:
            return None
        return [(p.x, p.y) for p in self.points]


class ZoneTemplateDocument(Document):
    """A hand-aligned zone layout shared by every drawing of one sheet template.

    Only zones the user has explicitly pinned are stored. An absent key means "keep
    detecting" rather than "no zone" — that distinction is what lets a partially-aligned
    template be useful instead of blanking the zones nobody has gotten to yet.
    """

    signature: str = Field(..., description="Sheet-template identity; see zone_signature().")
    name: str = Field(default="", description="Human-editable label. Surfaces signature collisions.")
    zones: dict[str, ZoneFractions] = Field(
        default_factory=dict,
        description="Pinned zones only, keyed by zone name. Absent = keep detecting.",
    )
    is_default: bool = Field(
        default=False,
        description=(
            "Global fallback template for sheets with no signature-specific match. At most one "
            "document has this True (enforced at the set-default endpoint). Pre-existing docs "
            "without the key parse as False, so no migration is needed."
        ),
    )
    updated_by: Optional[str] = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "zone_templates"
        indexes = [
            IndexModel([("signature", ASCENDING)], unique=True),
        ]


def zone_signature(render_bounds: list[float] | tuple) -> Optional[str]:
    """Derives a sheet-template identity from render_bounds.

    Currently the bucketed aspect ratio. **Known limitation, recorded rather than hidden:**
    every A-series sheet is 1.414, so two genuinely different layouts printed on A-series
    paper collide into one template. That is acceptable for a single company's drawing
    standard (the actual corpus) and is why the document carries an editable `name` — a
    collision should at least be visible. Refining this means adding discriminators here;
    do not treat matching aspect ratio as proof of matching layout anywhere in user-facing
    copy.
    """
    if not render_bounds or len(render_bounds) != 4:
        return None
    x0, y0, x1, y1 = (float(v) for v in render_bounds)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    return f"aspect-{round(w / h, 3):.3f}"
