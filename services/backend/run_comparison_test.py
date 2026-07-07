import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import sys
import os

# Add g:\APP DEVELOPMENT\ai-2d-checker to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from services.backend.api.routers.audits import perform_physical_comparison
    from services.backend.api.schemas import PhysicalComparisonRequest
    from services.backend.domain.models.drawing_document import DrawingDocument
    from services.backend.domain.models.extracted_entity import ExtractedEntity
except (ImportError, ModuleNotFoundError):
    try:
        from api.routers.audits import perform_physical_comparison
        from api.schemas import PhysicalComparisonRequest
        from domain.models.drawing_document import DrawingDocument
        from domain.models.extracted_entity import ExtractedEntity
    except Exception:
        sys.path.append('services/backend')
        from api.routers.audits import perform_physical_comparison
        from api.schemas import PhysicalComparisonRequest
        from domain.models.drawing_document import DrawingDocument
        from domain.models.extracted_entity import ExtractedEntity

async def main():
    from services.backend.infrastructure.database.connection import db_manager
    await db_manager.connect()
    
    # Use CR19061U01 assembly drawings
    ref_id = "6a4c9136d3519ef21ef800de"
    rev_id = "6a4c914ad3519ef21ef8120f"
    
    req = PhysicalComparisonRequest(
        reference_drawing_id=ref_id,
        drawing_id=rev_id
    )
    
    print("Running physical comparison endpoint logic...")
    res = await perform_physical_comparison(req)
    print("\nSUCCESS!")
    print("title_block status:", res.data.title_block.status)
    print("title_block difference_summary:", res.data.title_block.difference_summary)
    print("title_block reference_content:")
    print(repr(res.data.title_block.reference_content))
    print("title_block revision_content:")
    print(repr(res.data.title_block.revision_content))

if __name__ == '__main__':
    asyncio.run(main())
