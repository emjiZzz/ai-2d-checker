import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie, Document
from pydantic import Field

class DummyModel(Document):
    name: str

    class Settings:
        name = "dummy"

async def test():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_db"]
    try:
        await init_beanie(database=db, document_models=[DummyModel])
        print("SUCCESS")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test())
