import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['ai_2d_checker']
    col = db['ComparisonResult']
    docs = await col.count_documents({})
    print(f"ComparisonResult count: {docs}")
    names = await db.list_collection_names()
    print(f"Collections: {names}")

asyncio.run(main())
