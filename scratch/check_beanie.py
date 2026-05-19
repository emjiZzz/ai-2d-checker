import sys
import asyncio
from pathlib import Path

workspace_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace_path))

from motor.motor_asyncio import AsyncIOMotorClient

# Apply monkey patch!
AsyncIOMotorClient.append_metadata = lambda self, *args, **kwargs: None

from beanie import init_beanie
from services.backend.domain.models import __all_models__

async def test_connect():
    try:
        client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
        db = client["ai_2d_checker"]
        print("Initializing beanie...")
        await init_beanie(database=db, document_models=__all_models__)
        print("Success!")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test_connect())
