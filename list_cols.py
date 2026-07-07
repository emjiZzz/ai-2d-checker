import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['ai_2d_checker']
    cols = await db.list_collection_names()
    print('Available collections:')
    for col in cols:
        print(f'  {col}')

asyncio.run(main())
