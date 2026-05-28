import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['ai_2d_checker']
    drawings = await db['drawing_documents'].find().to_list(100)
    print('Uploaded Drawings:')
    for d in drawings:
        print(f'  ID: {d.get("_id")}, Name: {d.get("file_name")}')

asyncio.run(main())
