import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['ai_2d_checker']
    docs = await db.drawings.find({'filename': {'$regex': 'CMB3370'}}).to_list(10)
    for d in docs:
        print(f"ID: {d['id']}, Filename: {d['filename']}")
    await client.close()

asyncio.run(main())
