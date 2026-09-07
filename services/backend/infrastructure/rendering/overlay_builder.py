from typing import Any

from ...domain.models.audit_violation import AuditViolation
from ...logger import logger


class OverlayBuilder:
    """
    Constructs high-visibility canvas overlays representing audit violations,
    missing items, and annotation regions.
    """

    SEVERITY_COLORS = {
        "critical": "#FF0000",
        "high": "#FFA500",
        "medium": "#FFFF00",
        "low": "#00FFFF",
        "info": "#00FF00"
    }

    @staticmethod
    def build_violation_overlays(violations: list[AuditViolation]) -> list[dict[str, Any]]:
        """
        Maps AuditViolation documents into frontend-renderable geometric overlays.
        """
        overlays = []
        for v in violations:
            if not v.coordinates:
                continue

            color = OverlayBuilder.SEVERITY_COLORS.get(v.severity.lower(), "#FF00FF")
            
            overlays.append({
                "id": f"overlay_{v.id}",
                "violation_id": str(v.id),
                "severity": v.severity,
                "category": v.category,
                "description": v.description,
                "coordinates": v.coordinates,
                "color": color,
                "opacity": 0.5
            })
            
        logger.info(f"Built {len(overlays)} violation overlay graphics.")
        return overlays
