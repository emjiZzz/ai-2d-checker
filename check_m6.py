# -*- coding: utf-8 -*-
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['ai_2d_checker']
    col = db['audit_results']
    docs = await col.find().sort("created_at", -1).to_list(1)
    if docs:
        r = docs[0]
        print(f"Doc ID: {r['_id']}, Date: {r.get('created_at')}")
        parsed = r.get("ai_results", r)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        markings = parsed.get("canvas_markings", [])
        for m in markings:
            if m.get("category") in ("title_block", "bill_of_materials"):
                print(json.dumps(m, ensure_ascii=False))
    else:
        print("no docs")
asyncio.run(main())
