import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["ai_2d_checker"]
    entities_col = db["extracted_entities"]
    
    all_ents = await entities_col.find({}).to_list(length=50000)
    for e in all_ents:
        t = e.get("properties", {}).get("text", "")
        geom = e.get('geometry')
        if geom:
            ins = geom.get('insert')
            if ins and len(ins) >= 2:
                # Target the area around Unit No.
                if 0 < ins[0] < 300 and 1300 < ins[1] < 1500:
                    print(f"TEXT: {repr(t)} | LAYER: {e.get('layer')} | GEOM: {ins} | TYPE: {e.get('entity_type')}")
        
asyncio.run(test())
