"""
Hand-aligned zone templates.

A template is one sheet layout's zone boxes, stored as fractions of render_bounds so it
applies to every drawing sharing that layout regardless of scale. See
docs/zone-template-alignment-implementation-plan.md.

Deliberately separate from GET /drawings/{id}/zones: that endpoint reports what the detector
*found* on one drawing, this one stores what a human *decided* for a whole template. Keeping
them apart is what lets the overlay show both and mark which is which.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...domain.models.zone_template import ZoneFractions, ZoneTemplateDocument
from ...logger import logger
from ..dependencies import get_auth_token
from ..schemas import StandardResponse

router = APIRouter()


class ZoneTemplateResponse(BaseModel):
    signature: str
    name: str
    zones: dict[str, ZoneFractions]
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class ZoneTemplateUpsertRequest(BaseModel):
    name: str = Field(default="")
    zones: dict[str, ZoneFractions] = Field(
        default_factory=dict,
        description="Pinned zones only. Omitting a zone means 'keep detecting it', which is "
                    "not the same as pinning it to its detected position.",
    )
    updated_by: Optional[str] = None


@router.get(
    "/zone-templates/{signature}",
    response_model=StandardResponse[Optional[ZoneTemplateResponse]],
    summary="Fetch the hand-aligned zone template for a sheet signature",
    dependencies=[Depends(get_auth_token)],
)
async def get_zone_template(signature: str):
    """Returns null data when no template exists.

    Absence is the normal case for any sheet nobody has aligned yet, so it is a 200 with
    null rather than a 404 — the client treats a 404 as an error worth surfacing, and
    "nobody has aligned this layout" is not an error.
    """
    doc = await ZoneTemplateDocument.find_one(ZoneTemplateDocument.signature == signature)
    if not doc:
        return StandardResponse(success=True, data=None)

    return StandardResponse(
        success=True,
        data=ZoneTemplateResponse(
            signature=doc.signature,
            name=doc.name,
            zones=doc.zones,
            updated_by=doc.updated_by,
            updated_at=doc.updated_at,
        ),
    )


@router.put(
    "/zone-templates/{signature}",
    response_model=StandardResponse[ZoneTemplateResponse],
    summary="Create or replace the zone template for a sheet signature",
    dependencies=[Depends(get_auth_token)],
)
async def upsert_zone_template(signature: str, payload: ZoneTemplateUpsertRequest):
    """Upsert, not append: `zones` replaces the stored set wholesale.

    A merge would make un-pinning a zone impossible — the client would have no way to say
    "stop pinning this one, go back to detecting it" except by sending a sentinel.
    """
    doc = await ZoneTemplateDocument.find_one(ZoneTemplateDocument.signature == signature)
    if doc:
        doc.name = payload.name or doc.name
        doc.zones = payload.zones
        doc.updated_by = payload.updated_by
        doc.updated_at = datetime.utcnow()
        await doc.save()
    else:
        doc = ZoneTemplateDocument(
            signature=signature,
            name=payload.name,
            zones=payload.zones,
            updated_by=payload.updated_by,
        )
        await doc.insert()

    logger.info(
        f"Zone template '{signature}' saved with {len(payload.zones)} pinned zone(s): "
        f"{sorted(payload.zones)}"
    )
    return StandardResponse(
        success=True,
        data=ZoneTemplateResponse(
            signature=doc.signature,
            name=doc.name,
            zones=doc.zones,
            updated_by=doc.updated_by,
            updated_at=doc.updated_at,
        ),
    )
