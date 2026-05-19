from typing import Any, Dict
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extraction_job import ExtractionJob
from ...domain.models.extracted_entity import ExtractedEntity

class CADDiagnostics:
    """
    Diagnostics service to aggregate, format, and report CAD extraction timing metrics,
    durations, entity statistics, and error logs.
    """
    @staticmethod
    async def get_job_diagnostics(job_id: str) -> Dict[str, Any]:
        """
        Gathers complete execution details, times, and errors for a specific extraction job.
        """
        job = await ExtractionJob.get(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}
            
        drawing = await DrawingDocument.get(job.drawing_id)
        
        # Count actual entities stored in DB matching this job
        entities_count = await ExtractedEntity.find(ExtractedEntity.job_id == job_id).count()
        
        # Break down count by type
        by_type_counts = {}
        if job.status == "completed":
            # Direct count aggregation
            for etype in ["line", "circle", "arc", "polyline", "dimension", "text", "block", "layer"]:
                count = await ExtractedEntity.find(
                    ExtractedEntity.job_id == job_id,
                    ExtractedEntity.entity_type == etype
                ).count()
                if count > 0:
                    by_type_counts[etype] = count

        return {
            "success": True,
            "job_id": job_id,
            "drawing_id": job.drawing_id,
            "file_name": drawing.file_name if drawing else "unknown",
            "status": job.status,
            "error_message": job.error_message,
            "timestamps": {
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            },
            "durations": {
                "conversion_seconds": job.conversion_duration_seconds,
                "parsing_seconds": job.parsing_duration_seconds,
                "total_seconds": job.total_duration_seconds
            },
            "database_stats": {
                "total_entities_persisted": entities_count,
                "entity_types_breakdown": by_type_counts
            },
            "metadata_diagnostics": job.diagnostics
        }
