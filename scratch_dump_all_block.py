import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import sys

if not hasattr(AsyncIOMotorClient, "append_metadata"):
    AsyncIOMotorClient.append_metadata = lambda self, *args, **kwargs: None

sys.path.append(r"g:\APP DEVELOPMENT\ai-2d-checker")

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity

def safe_decode(text):
    if not text:
        return ""
    try:
        b = text.encode('latin1')
        return b.decode('cp932')
    except Exception:
        try:
            b = text.encode('utf-8')
            return b.decode('cp932')
        except Exception:
            return text

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    await init_beanie(
        database=client['ai_2d_checker'],
        document_models=[DrawingDocument, ExtractedEntity]
    )
    
    ref_id = "6a0e93c965fe35366de1ceab"
    rev_id = "6a0e93e265fe35366de1dfec"
    
    for label, drawing_id in [("REFERENCE", ref_id), ("REVISION", rev_id)]:
        print(f"\n=================== {label} DRAWING ({drawing_id}) ===================")
        entities = await ExtractedEntity.find(
            ExtractedEntity.drawing_id == drawing_id,
            ExtractedEntity.entity_type == "text"
        ).to_list()
        
        # Filter: bottom-right quadrant
        # Let's check coord_scale:
        coord_scale = 1.0
        for e in entities:
            if e.geometry:
                ins = e.geometry.get("insert") or [0, 0, 0]
                if ins[0] > 1000:
                    coord_scale = 2.0
                    break
        
        print(f"Detected coord_scale = {coord_scale}")
        
        block_entities = []
        for e in entities:
            geom = e.geometry or {}
            ins = geom.get("insert") or [0, 0, 0]
            x, y = ins[0], ins[1]
            # Since coord_scale could be 2.0, the coordinates are scaled.
            # In ref_drawing, X is around 1100-1600, Y is around 40-120.
            # In rev_drawing, X is around 550-800, Y is around 20-60.
            if coord_scale == 2.0:
                is_in_block = (x > 1000 and y < 200)
            else:
                is_in_block = (x > 500 and y < 100)
                
            if is_in_block:
                block_entities.append((x, y, e))
                
        # Sort by Y descending, then X ascending
        block_entities.sort(key=lambda item: (-item[1], item[0]))
        
        for x, y, e in block_entities:
            txt = e.properties.get("text", "")
            decoded = safe_decode(txt)
            print(f"({x:7.1f}, {y:7.1f}) | Raw: {repr(txt):<25} | Decoded: {repr(decoded)}")

if __name__ == '__main__':
    asyncio.run(main())
