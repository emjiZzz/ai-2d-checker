from typing import List, Dict, Any
from ....domain.models.audit_violation import AuditViolation
from ....domain.models.drawing_document import DrawingDocument
from ....domain.models.extracted_entity import ExtractedEntity

class RuleContext:
    def __init__(
        self,
        audit_session_id: str,
        drawing: DrawingDocument,
        entities: List[ExtractedEntity],
        entities_by_type: Dict[str, List[ExtractedEntity]],
        all_text_contents: List[str]
    ):
        self.audit_session_id = audit_session_id
        self.drawing = drawing
        self.entities = entities
        self.entities_by_type = entities_by_type
        self.all_text_contents = all_text_contents

    def get_text_content(self, ent: ExtractedEntity) -> str:
        props = ent.properties or {}
        return (props.get("text") or props.get("value") or "").strip()
