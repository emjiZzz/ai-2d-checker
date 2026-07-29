from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, IndexModel


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

    @field_validator("xMin", "xMax", "yMin", "yMax", mode="before")
    @classmethod
    def clamp_bounds(cls, v: float) -> float:
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return v


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
