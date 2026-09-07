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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...domain.models.zone_template import (
    VALID_ZONE_KEYS,
    ZoneFractions,
    ZoneTemplateDocument,
)
from ...logger import logger
from ..dependencies import get_auth_token
from ..schemas import StandardResponse

router = APIRouter()


class ZoneTemplateResponse(BaseModel):
    signature: str
    name: str
    zones: dict[str, ZoneFractions]
    is_default: bool = False
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

    @field_validator("zones")
    @classmethod
    def strip_non_zone_keys(
        cls, zones: dict[str, ZoneFractions]
    ) -> dict[str, ZoneFractions]:
        """Drop any key that isn't a real comparison zone before persisting.

        A save path that serializes the whole zones *response* object (which also carries
        "drawing_id"/"render_bounds") would otherwise pollute the template with keys nothing
        consumes. Stripping rather than 400-ing keeps existing clients working; the polluted
        keys just don't get stored.
        """
        polluting = [k for k in zones if k not in VALID_ZONE_KEYS]
        if polluting:
            logger.warning(
                f"Ignoring non-zone keys in zone-template save: {sorted(polluting)}"
            )
        return {k: v for k, v in zones.items() if k in VALID_ZONE_KEYS}


class SetDefaultRequest(BaseModel):
    is_default: bool = Field(
        ...,
        description="True designates this template as the global fallback (clearing any prior "
                    "default); False clears it.",
    )


def _to_response(doc: ZoneTemplateDocument) -> ZoneTemplateResponse:
    """Single mapper so every handler returns the same shape — including is_default."""
    return ZoneTemplateResponse(
        signature=doc.signature,
        name=doc.name,
        zones=doc.zones,
        is_default=doc.is_default,
        updated_by=doc.updated_by,
        updated_at=doc.updated_at,
    )


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

    return StandardResponse(success=True, data=_to_response(doc))


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
    return StandardResponse(success=True, data=_to_response(doc))


@router.get(
    "/zone-templates",
    response_model=StandardResponse[list[ZoneTemplateResponse]],
    summary="List all hand-aligned zone templates",
    dependencies=[Depends(get_auth_token)],
)
async def list_zone_templates():
    """Returns all saved zone templates ordered by last update time descending."""
    docs = await ZoneTemplateDocument.find_all().sort("-updated_at").to_list()
    return StandardResponse(success=True, data=[_to_response(doc) for doc in docs])


@router.get(
    "/zone-templates-default",
    response_model=StandardResponse[Optional[ZoneTemplateResponse]],
    summary="Fetch the global default (fallback) zone template, if one is designated",
    dependencies=[Depends(get_auth_token)],
)
async def get_default_zone_template():
    """Returns the template flagged is_default, or null when none is designated.

    A dedicated path (not `/zone-templates/{signature}`) so 'default' can't be mistaken for a
    signature. Used by the editor to show what the audit will fall back to on an unmatched sheet.
    """
    doc = await ZoneTemplateDocument.find_one(ZoneTemplateDocument.is_default == True)  # noqa: E712
    if not doc:
        return StandardResponse(success=True, data=None)
    return StandardResponse(success=True, data=_to_response(doc))


@router.put(
    "/zone-templates/{signature}/default",
    response_model=StandardResponse[ZoneTemplateResponse],
    summary="Designate (or clear) a template as the global default fallback",
    dependencies=[Depends(get_auth_token)],
)
async def set_default_zone_template(signature: str, payload: SetDefaultRequest):
    """Enforces the single-default invariant: setting one default clears any prior one.

    Returns 404 if the signature has no template. Clearing (is_default=False) only unsets this
    template — sheets then fall back to plain detection, same as before any default existed.
    """
    doc = await ZoneTemplateDocument.find_one(ZoneTemplateDocument.signature == signature)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No zone template found for signature '{signature}'.",
        )

    if payload.is_default:
        # Clear every other default first, so at most one document is ever the default.
        async for other in ZoneTemplateDocument.find(
            ZoneTemplateDocument.is_default == True,  # noqa: E712
            ZoneTemplateDocument.signature != signature,
        ):
            other.is_default = False
            await other.save()

    doc.is_default = payload.is_default
    await doc.save()
    logger.info(
        f"Zone template '{signature}' is_default set to {payload.is_default}."
    )
    return StandardResponse(success=True, data=_to_response(doc))


@router.delete(
    "/zone-templates/{signature}",
    response_model=StandardResponse[bool],
    summary="Delete a hand-aligned zone template by signature",
    dependencies=[Depends(get_auth_token)],
)
async def delete_zone_template(signature: str):
    """Deletes a saved zone template by signature."""
    doc = await ZoneTemplateDocument.find_one(ZoneTemplateDocument.signature == signature)
    if doc:
        await doc.delete()
        logger.info(f"Zone template '{signature}' deleted.")
        return StandardResponse(success=True, data=True)
    return StandardResponse(success=True, data=False)

