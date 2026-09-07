from datetime import datetime

from fastapi import APIRouter, Depends, Header

from ...domain.models.annotation_document import AnnotationDocument
from ...domain.models.drawing_document import DrawingDocument
from ...infrastructure.cad.coordinate_stamp import has_drifted, stamp_pair
from ...logger import logger
from ..dependencies import get_auth_token, get_or_404, resolve_username
from ..schemas import (
    AnnotationResponse,
    CreateAnnotationRequest,
    StandardResponse,
    UpdateAnnotationRequest,
)

router = APIRouter()


async def _load_drawing(drawing_id: str) -> DrawingDocument | None:
    """Fetch the drawing a coordinate belongs to, tolerating a missing record.

    A malformed or deleted drawing_id must not block annotation CRUD -- the point is
    simply stamped with default provenance instead.
    """
    try:
        return await DrawingDocument.get(drawing_id)
    except Exception as exc:
        logger.debug(f"Could not load drawing {drawing_id} for coordinate stamping: {exc}")
        return None


def _to_response(a: AnnotationDocument, drawing: DrawingDocument | None = None) -> AnnotationResponse:
    return AnnotationResponse(
        id=str(a.id),
        review_session_id=a.review_session_id,
        drawing_id=a.drawing_id,
        author_id=a.author_id,
        annotation_type=a.annotation_type,
        content=a.content,
        severity=a.severity,
        coordinates=a.coordinates,
        target_entity_ids=a.target_entity_ids,
        violation_id=a.violation_id,
        status=a.status,
        pen_type=a.pen_type,
        created_at=a.created_at,
        updated_at=a.updated_at,
        coordinate_drift=has_drifted(a.coordinates, drawing),
    )


@router.post(
    "/annotations",
    response_model=StandardResponse[AnnotationResponse],
    summary="Create a review annotation/pin",
    dependencies=[Depends(get_auth_token)],
)
async def create_annotation(
    payload: CreateAnnotationRequest,
    x_session_token: str | None = Header(None, alias="X-Session-Token"),
):
    drawing = await _load_drawing(payload.drawing_id)
    annotation = AnnotationDocument(
        review_session_id=payload.review_session_id,
        drawing_id=payload.drawing_id,
        author_id=resolve_username(x_session_token) or "unknown",
        annotation_type=payload.annotation_type,
        content=payload.content,
        severity=payload.severity,
        coordinates=stamp_pair(payload.coordinates, drawing),
        target_entity_ids=payload.target_entity_ids,
        violation_id=payload.violation_id,
        pen_type=payload.pen_type,
    )
    await annotation.save()
    logger.info(f"Annotation created: {annotation.id} on drawing {annotation.drawing_id} by {annotation.author_id}")
    return StandardResponse(success=True, data=_to_response(annotation, drawing))


@router.get(
    "/annotations",
    response_model=StandardResponse[list[AnnotationResponse]],
    summary="List annotations for a drawing or review session",
    dependencies=[Depends(get_auth_token)],
)
async def list_annotations(
    drawing_id: str | None = None,
    review_session_id: str | None = None,
):
    query = AnnotationDocument.find_all()
    if drawing_id:
        query = AnnotationDocument.find(AnnotationDocument.drawing_id == drawing_id)
    elif review_session_id:
        query = AnnotationDocument.find(AnnotationDocument.review_session_id == review_session_id)

    annotations = await query.sort(-AnnotationDocument.created_at).to_list()

    # Drift is per-drawing; a review session can span several, so resolve each once.
    drawing_cache: dict[str, DrawingDocument | None] = {}
    responses = []
    for a in annotations:
        if a.drawing_id not in drawing_cache:
            drawing_cache[a.drawing_id] = await _load_drawing(a.drawing_id)
        responses.append(_to_response(a, drawing_cache[a.drawing_id]))

    return StandardResponse(success=True, data=responses)


@router.get(
    "/annotations/{annotation_id}",
    response_model=StandardResponse[AnnotationResponse],
    summary="Get a single annotation",
    dependencies=[Depends(get_auth_token)],
)
async def get_annotation(annotation_id: str):
    annotation = await get_or_404(AnnotationDocument, annotation_id, "Annotation not found.")
    drawing = await _load_drawing(annotation.drawing_id)
    return StandardResponse(success=True, data=_to_response(annotation, drawing))


@router.patch(
    "/annotations/{annotation_id}",
    response_model=StandardResponse[AnnotationResponse],
    summary="Update an annotation's content, status, or placement",
    dependencies=[Depends(get_auth_token)],
)
async def update_annotation(annotation_id: str, payload: UpdateAnnotationRequest):
    annotation = await get_or_404(AnnotationDocument, annotation_id, "Annotation not found.")

    drawing = await _load_drawing(annotation.drawing_id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        # A move re-stamps provenance against the drawing as it is now, which also
        # clears any drift flag the old position carried.
        if field == "coordinates":
            value = stamp_pair(value, drawing)
        setattr(annotation, field, value)

    annotation.updated_at = datetime.utcnow()
    await annotation.save()
    return StandardResponse(success=True, data=_to_response(annotation, drawing))


@router.delete(
    "/annotations/{annotation_id}",
    response_model=StandardResponse[dict],
    summary="Delete an annotation",
    dependencies=[Depends(get_auth_token)],
)
async def delete_annotation(annotation_id: str):
    annotation = await get_or_404(AnnotationDocument, annotation_id, "Annotation not found.")
    await annotation.delete()
    logger.info(f"Annotation deleted: {annotation_id}")
    return StandardResponse(success=True, data={"deleted": True})
