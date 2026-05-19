from typing import Any, Dict, List
from ...logger import logger
from ...domain.models.annotation_document import AnnotationDocument

class AnnotationMapper:
    """
    Transforms backend AnnotationDocument models into frontend-renderable
    pin and region payloads.
    """
    
    @staticmethod
    def map_annotations(annotations: List[AnnotationDocument]) -> List[Dict[str, Any]]:
        results = []
        for ann in annotations:
            results.append({
                "id": str(ann.id),
                "type": ann.annotation_type,
                "content": ann.content,
                "severity": ann.severity,
                "coordinates": ann.coordinates,
                "author": ann.author_id,
                "status": ann.status,
                "target_entities": ann.target_entity_ids,
                "timestamp": ann.created_at.isoformat()
            })
            
        logger.debug(f"Mapped {len(results)} annotations for frontend canvas.")
        return results
