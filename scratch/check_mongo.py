import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    try:
        client = AsyncIOMotorClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=2000)
        res = await client.admin.command("ping")
        print("MongoDB Ping Success:", res)
    except Exception as e:
        print("MongoDB Ping Failed:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
