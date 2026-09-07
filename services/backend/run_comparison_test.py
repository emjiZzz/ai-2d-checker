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
    
    # Query database for available drawings
    drawings = await DrawingDocument.find_all().limit(2).to_list()
    if len(drawings) < 2:
        print("ERROR: Need at least 2 drawings in the database to run the comparison test.")
        return
        
    ref_id = "6a5f09d6f3fcd214b5e123b9"
    rev_id = "6a5f09eaf3fcd214b5e125cb"

    req = PhysicalComparisonRequest(
        reference_drawing_id=ref_id,
        drawing_id=rev_id,
        comparison_method="deterministic"
    )
    
    print("Running physical comparison endpoint logic...")
    res = await perform_physical_comparison(req)
    print("\nSUCCESS!")
    print("bill_of_materials status:", res.data.bill_of_materials.status)
    print("bill_of_materials difference_summary:", res.data.bill_of_materials.difference_summary)
    print("bill_of_materials discrepancy_details:", res.data.bill_of_materials.engineering_discrepancy_details)
    print("bill_of_materials reference_content:")
    print(repr(res.data.bill_of_materials.reference_content)[:100] + "...")

if __name__ == '__main__':
    asyncio.run(main())
