import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie, Document
import sys
import logging

# Add services/backend to path
sys.path.append('services/backend')

from api.v1 import perform_physical_comparison
from api.schemas import PhysicalComparisonRequest, DrawingDocument, ExtractedEntity

logging.basicConfig(level=logging.INFO)

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    await init_beanie(
        database=client['ai_2d_checker'],
        document_models=[DrawingDocument, ExtractedEntity]
    )
    
    # Let's use the CR19061U01 assembly drawings
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

asyncio.run(main())
