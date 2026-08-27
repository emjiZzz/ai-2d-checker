"""Report export: the drawing page, as vectors.

One route, `POST /export/drawings/{drawing_id}/vector-sheet`, returning a single-page PDF whose
CAD geometry is real vector paths and whose text is selectable and searchable. The desktop app
binds it in front of its own checklist pages.

## Why the markers come from the client

The engineer's marks are already resolved in the workspace store, in CAD coordinates, filtered
to what is actually drawn on the canvas (retracted markings excluded, engine markers suppressed
in a manual-check room). Re-deriving that server-side would be a second opinion about what the
sheet shows, and the report exists to be evidence of the review — so it takes the marks the
canvas drew rather than recomputing them from the database.

The entities, by contrast, are read server-side from `load_entities`: they are the stored
extraction, which is what the canvas drew from.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ...core.security import sandboxed_path
from ...domain.models.drawing_document import DrawingDocument
from ...infrastructure.rendering.vector_pdf_exporter import (
    A4_LANDSCAPE,
    PageSpec,
    SheetMarker,
    TextSource,
    render_vector_sheet,
)
from ...infrastructure.storage.entity_cache import load_entities
from ...logger import logger
from ..dependencies import get_auth_token, get_or_404

router = APIRouter()

#: A sheet with more marks than this is not a sheet anyone is reading, and each one costs a
#: vector badge plus a text run. Bounded so a malformed client cannot ask for a 200 MB page.
_MAX_MARKERS = 2000


class MarkerPayload(BaseModel):
    """One review mark, in the drawing's paper-space CAD frame (Y-up).

    ⚠ NOT canvas pixels and NOT `render_bounds` fractions — those are Y-down, and a mirrored
    overlay looks plausible. `renderManualMarkings.ts` holds the canvas side of this contract.
    """

    x: float
    y: float
    status: str = "MISMATCHED"
    label: str = Field("", max_length=200)


class VectorSheetRequest(BaseModel):
    markers: list[MarkerPayload] = Field(default_factory=list, max_length=_MAX_MARKERS)
    #: Millimetres. Defaults to A4 landscape, matching `REPORT_PAGE_MM` on the desktop side.
    page_width_mm: float | None = Field(None, gt=0, le=2000)
    page_height_mm: float | None = Field(None, gt=0, le=2000)
    margin_mm: float | None = Field(None, ge=0, le=50)


@router.post(
    "/export/drawings/{drawing_id}/vector-sheet",
    summary="Render one drawing as a single-page vector PDF with a searchable text layer",
    dependencies=[Depends(get_auth_token)],
    responses={200: {"content": {"application/pdf": {}}}},
    response_class=Response,
)
async def export_vector_sheet(drawing_id: str, payload: VectorSheetRequest) -> Response:
    drawing: DrawingDocument = await get_or_404(
        DrawingDocument, drawing_id, "Drawing not found"
    )

    if (drawing.format or "").lower() != "dxf":
        # PDF- and STEP-sourced drawings reach the same room and the same report, and neither
        # has a DXF to render. 422 rather than a crash inside the renderer.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Vector export needs a DXF source; this drawing is '{drawing.format}'.",
        )

    if not drawing.file_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Drawing has no stored source file.",
        )

    source = sandboxed_path(drawing.file_path)
    if not source.exists():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Drawing's source file is no longer on disk.",
        )

    entities = await load_entities(drawing_id)
    if not entities:
        # Distinguished from "rendered with no text": a drawing still extracting would otherwise
        # come back as a correct-looking page with an empty text layer, and nothing would say so.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Drawing entities have not been extracted yet.",
        )

    page = A4_LANDSCAPE
    if payload.page_width_mm and payload.page_height_mm:
        page = PageSpec(
            width_mm=payload.page_width_mm,
            height_mm=payload.page_height_mm,
            margin_mm=payload.margin_mm if payload.margin_mm is not None else A4_LANDSCAPE.margin_mm,
        )

    markers = [SheetMarker(m.x, m.y, m.status, m.label) for m in payload.markers]
    payload_entities = [
        {"entity_type": e.entity_type, "properties": e.properties, "geometry": e.geometry}
        for e in entities
    ]

    # Offloaded, like every other blocking step that shares this event loop. A sheet takes
    # seconds and this route is served from the same loop as the rest of the API, so inline it
    # would stall every other request for its full duration -- the defect recorded in
    # `Gotcha - The Background Queue Was Not a Background Thread`. Safe to run concurrently:
    # `vector_pdf_exporter` drives the OO `Figure` API, not the `pyplot` state machine.
    #
    # `TextSource.LAYER` makes the searchable layer the VISIBLE text instead of a second, hidden
    # copy under ezdxf's glyphs. Measured on this corpus's six densest sheets: **3.4x to 8.0x**
    # end-to-end (28.1 s -> 7.5 s on the largest), a fifth of the file size, and real selectable
    # text rather than paths. It matters most for the sheets nobody has exported yet -- ezdxf
    # costs ~44 ms per string against the layer's 2.18 ms, so it changes how the export SCALES,
    # and an assembly is a lot of strings.
    #
    # ⚠ It is a REQUEST, not a setting. `_resolve_text_source` downgrades it to `OUTLINES` for
    # any drawing whose extraction cannot place every string -- which is 20 of the 65 stored
    # drawings, at schema v2, predating `render_text_point`. Those stay correct and stay slow;
    # `tools/extraction_status.py` lists them and `/reextract` fixes one.
    #
    # To revert the report to ezdxf-drawn text, drop this argument. Nothing else depends on it.
    try:
        pdf_bytes = await asyncio.to_thread(
            render_vector_sheet, source,
            entities=payload_entities, markers=markers, page=page,
            text_source=TextSource.LAYER,
        )
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001 -- surfaced as a 500 with a logged cause, never a
        # half-written PDF. A truncated PDF opens in some viewers and not others, which reads as
        # a viewer problem rather than as a failed export.
        logger.error(f"Vector sheet export failed for {drawing_id}: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vector sheet could not be rendered.",
        ) from err

    stem = (drawing.file_name or drawing_id).rsplit(".", 1)[0]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{stem}-sheet.pdf"'},
    )
