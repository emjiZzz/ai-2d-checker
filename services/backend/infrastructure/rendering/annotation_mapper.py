from typing import Any

from ...domain.models.annotation_document import AnnotationDocument
from ...logger import logger


class AnnotationMapper:
    """
    Transforms backend AnnotationDocument models into frontend-renderable
    pin and region payloads.
    """
    
    @staticmethod
    def map_annotations(annotations: list[AnnotationDocument]) -> list[dict[str, Any]]:
        results = []
        for ann in annotations:
            results.append({
                "id": str(ann.id),
                "type": ann.annotation_type,
                "content": ann.content,
                "severity": ann.severity,
                "coordinates": ann.coordinates.as_pair() if ann.coordinates else None,
                "author": ann.author_id,
                "status": ann.status,
                "target_entities": ann.target_entity_ids,
                "timestamp": ann.created_at.isoformat()
            })
            
        logger.debug(f"Mapped {len(results)} annotations for frontend canvas.")
        return results
