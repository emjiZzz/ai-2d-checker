import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["ai_2d_checker"]
    entities_col = db["extracted_entities"]
    
    all_ents = await entities_col.find({}).to_list(length=50000)
    
    label_coords = []
    val_coords = []
    
    for e in all_ents:
        t = e.get("properties", {}).get("text", "")
        if not t: continue
        t = t.lower()
        if "no." in t or "no" in t or t.strip() in ["11", "016"]:
            ins = e.get('geometry', {}).get('insert')
            print(f"TEXT: {repr(t)} | GEOM: {ins}")
        
asyncio.run(test())
