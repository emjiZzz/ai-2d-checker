import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    dbs = await client.list_database_names()
    print('Available databases:')
    for db in dbs:
        print(f'  {db}')

asyncio.run(main())
