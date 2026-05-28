import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import sys
import os

# Add g:\APP DEVELOPMENT\ai-2d-checker to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.backend.api.v1 import perform_physical_comparison
from services.backend.api.schemas import PhysicalComparisonRequest
from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    await init_beanie(
        database=client['ai_2d_checker'],
        document_models=[DrawingDocument, ExtractedEntity]
    )
    
    # Use CR19061U01 assembly drawings
    ref_id = "6a0e93c965fe35366de1ceab"
    rev_id = "6a0e93e265fe35366de1dfec"
    
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
