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
    entities = await ExtractedEntity.find(
        ExtractedEntity.drawing_id == ref_id,
        ExtractedEntity.entity_type == "text"
    ).to_list()
    
    for e in entities:
        txt = e.properties.get("text", "")
        decoded = safe_decode(txt)
        if "神" in decoded or "吉" in decoded:
            geom = e.geometry or {}
            ins = geom.get("insert") or [0, 0, 0]
            print(f"FOUND: raw={repr(txt)} decoded={repr(decoded)} pos=({ins[0]}, {ins[1]}) codepoints={[ord(c) for c in decoded]}")

if __name__ == '__main__':
    asyncio.run(main())
