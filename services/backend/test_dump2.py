import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys

async def test():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["ai_2d_checker"]
    entities_col = db["extracted_entities"]
    
    # Let's find single character texts
    all_ents = await entities_col.find({}).to_list(length=50000)
    for e in all_ents:
        t = e.get("properties", {}).get("text", "")
        geom = e.get('geometry')
        layer = e.get('layer', '')
        if t and len(t.strip()) <= 2:
            ins = geom.get('insert') if geom else None
            # Print if it's near the edge or just print all of them to see the layer
            print(f"TEXT: {repr(t)} | LAYER: {layer} | GEOM: {ins}")
        
asyncio.run(test())
