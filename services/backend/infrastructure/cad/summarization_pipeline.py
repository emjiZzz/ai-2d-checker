import json
import asyncio
import os
from typing import Any

from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...infrastructure.audit.comparison.gemini_client import execute_gemini_cascade
from ...infrastructure.audit.context_builder import build_structured_context, load_drawing_png
from ...config import settings
from ...logger import logger
from ...api.schemas import DrawingSummaryResponse
from ..storage.entity_cache import load_entities

class SummarizationPipeline:
    async def run(self, drawing_id: str) -> None:
        try:
            logger.info(f"Starting async 6-view summarization for Drawing ID: {drawing_id}")
            drawing = await DrawingDocument.get(drawing_id)
            if not drawing:
                logger.error(f"Drawing {drawing_id} not found for summarization.")
                return

            if drawing.status == "failed":
                logger.warning(f"Drawing {drawing_id} is marked as failed, skipping AI summarization.")
                return
                
            entities = await load_entities(drawing_id)
            structured_context = build_structured_context(entities, drawing)
            png_bytes = load_drawing_png(drawing_id)
            
            api_key = getattr(settings, "GEMINI_API_KEY", None)
            if not api_key:
                api_key = os.environ.get("GEMINI_API_KEY")
                
            if not api_key:
                logger.error("GEMINI_API_KEY not found. Skipping summarization.")
                return

            system_instruction = (
                "You are an expert mechanical engineering CAD auditor. "
                "Analyze the provided structured CAD context and the drawing rendering (if provided). "
                "Produce a highly detailed, component-level summary broken into the following exactly 6 views: "
                "1. Drawing Views: origin, alignment of views, line attributes, dimensions, hole properties, chamfer/radius, welding symbol, geometric tolerances, additional views, text attributes.\n"
                "2. Notes: standard notes and special notes.\n"
                "3. BOM: material type, specification, quantity, weight, balloons, remarks, numbering.\n"
                "4. Title Block: machine name, line name, scale, designed by, drawn by, quantity, job/ref numbers, rev code.\n"
                "5. ISO View: orientation, scale, location. IMPORTANT: ISO views might lack text labels and may not appear in the JSON context. You MUST visually inspect the provided drawing rendering (PNG) to see if a 3D isometric representation exists before concluding it is missing.\n"
                "6. Others: tree view properties/link, excel additional information.\n"
                "Format output strictly to the response schema."
            )
            
            contents = []
            if png_bytes:
                from google.genai import types
                contents.append(types.Part.from_bytes(data=png_bytes, mime_type="image/png"))
                
            contents.append(f"Drawing Metadata & Entities Context:\n{json.dumps(structured_context, indent=2)}")
            
            # Offload blocking Gemini SDK cascade to a background thread to unblock the main event loop
            response_text, _model_used = await asyncio.to_thread(
                execute_gemini_cascade,
                api_key,
                system_instruction,
                contents,
                DrawingSummaryResponse
            )
            
            # response_text is guaranteed to be a string that matches the Pydantic schema
            parsed_summary = json.loads(response_text)
            
            # Save strictly to the dedicated field, completely isolating it from the metadata overwrite bug
            drawing.ai_summary = parsed_summary
            await drawing.save()
            
            logger.info(f"Successfully generated and persisted 6-view AI summary for Drawing ID: {drawing_id}")
            
        except Exception as e:
            logger.error(f"Failed to generate AI summary for drawing {drawing_id}: {str(e)}")
            # Complete failure isolation: Do NOT fail the drawing document. ai_summary naturally remains None.
