from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

# Bump when the shape of `properties` / `geometry` changes such that previously
# extracted rows can no longer be interpreted the same way. Stored on the parent
# DrawingDocument so stale extractions are detectable without re-reading entities.
#
# v3: dimensions carry `geometry.render_text_point`, the text anchor harvested from the
# dimension's own geometry block. Rows written at v2 lack it and the canvas falls back to
# `text_point` — which sits ON the dimension line, so their measurements still draw through
# it. Strictly additive, so v2 rows remain readable; the bump is what makes "this drawing
# predates the fix and needs re-extracting" answerable, which is the field's whole purpose.
# The cure is `POST /drawings/{id}/reextract`, which keeps the drawing's id and history.
# v4: LEADER vertex chains carry their hookline — the landing segment that runs under the
# annotation text, which the DXF stores as `has_hookline`/`text_width` rather than as a vertex.
# Rows written at v3 or earlier stop short of their own label (17.1 paper units short on
# M745221N01's `6-9キリ` callout), which reads as a pointer that never arrives.
# v5: the leader landing is sized from the linked annotation's own width
# (`annotation_handle` -> MTEXT `width`) rather than the leader's `text_width`, which
# under-states it — 22.62 against 28.56 on M745221N01's revision, leaving the landing ending
# inside its own label. v4 rows have a landing that is short by that difference.
# v6: leaders carry `arrow_size` (DIMASZ from their dimstyle, viewport-scaled) so the canvas can
# draw the arrowhead. v5 rows have none, and their pointers end in a bare line at the feature.
# v7: an ANGULAR dimension's substituted text is converted from radians to degrees and given a
# degree sign. `actual_measurement` is radians for dim kinds 2 and 5, so v6 rows store `1.05` for
# a dimension the sheet reads as `60°` — a value printed nowhere on the drawing. Comparison is
# unaffected (it keys on `measurement` + kind, never this string), but anything showing the text
# to a person, or capturing it as ground truth via `EntityAddress.text`, is wrong on v6 rows.
# v8: a dimension's `geometry.render_fills` carried a synthetic triangle for open arrowhead blocks.
# v9: open arrowhead blocks (_OPEN30) remain wireframe strokes in `render_paths` without synthetic
# solid fills, matching original CAD drawings (iCAD SX / Japanese drafting) where arrowheads are not solid.
EXTRACTION_SCHEMA_VERSION = 9


class ExtractedEntity(Document):
    drawing_id: str = Field(..., description="Reference ID of the associated DrawingDocument")
    job_id: str = Field(..., description="Reference ID of the extraction pipeline job")
    entity_type: str = Field(..., description="Normalized CAD type: line, circle, arc, polyline, dimension, text, block, layer")
    layer: str = Field("0", description="Layer name the entity resides on")

    # Promoted out of `properties` so they can be indexed. Entity-handle lookup is
    # the addressing scheme for AI-grounded findings and canvas hit-testing; scanning
    # a nested dict field for it does not scale.
    handle: str | None = Field(None, description="Source DXF entity handle, unique within the drawing")
    parent_handle: str | None = Field(None, description="Handle of the owning INSERT when this entity came from an exploded block")
    space: str = Field("model", description="Coordinate space of `geometry`: 'model' or 'paper'")
    viewport_index: int = Field(-1, description="Index into the drawing's viewport transform, or -1 for identity/no viewport")

    properties: dict[str, Any] = Field(default_factory=dict, description="CAD metadata properties (start, end, radius, text, etc.)")
    geometry: dict[str, Any] = Field(default_factory=dict, description="Coordinates, length, bounds, or vectors")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "extracted_entities"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("job_id", ASCENDING)]),
            IndexModel([("entity_type", ASCENDING)]),
            IndexModel([("layer", ASCENDING)]),
            # Handle resolution is always scoped to one drawing.
            IndexModel([("drawing_id", ASCENDING), ("handle", ASCENDING)]),
            IndexModel([("drawing_id", ASCENDING), ("parent_handle", ASCENDING)]),
            # Layer/type filtering within a drawing backs the entity manifest and
            # the scene endpoint.
            IndexModel([("drawing_id", ASCENDING), ("entity_type", ASCENDING)]),
        ]
