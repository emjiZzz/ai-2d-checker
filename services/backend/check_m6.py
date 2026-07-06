import asyncio
import sys
import json
sys.path.append('i:/ai-2d-checker/services/backend')
from infrastructure.storage.mongo import get_database
from domain.models.comparison import ComparisonResult

async def run():
    await get_database()
    r = await ComparisonResult.find().sort('-created_at').first_or_none()
    if r:
        matches = [m for m in r.differences if 'M6' in str(m) or 'M6' in m.get('description', '') or 'キリ' in str(m)]
        print(json.dumps(matches, indent=2, ensure_ascii=False))
    else:
        print('No comparison result found')

asyncio.run(run())
