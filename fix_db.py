import asyncio
import sys
sys.path.append("i:/ai-2d-checker/services/backend")
from infrastructure.storage.mongo import get_database
from domain.models.extracted_entity import ExtractedEntity
from infrastructure.cad.entity_mapper import EntityMapper

async def fix_db():
    await get_database()
    docs = await ExtractedEntity.find().to_list()
    updated = 0
    for doc in docs:
        text = doc.properties.get("text", "")
        if text and "\\" in text and "W" in text:
            clean_text = EntityMapper._clean_mtext_content(text)
            if clean_text != text:
                doc.properties["text"] = clean_text
                await doc.save()
                updated += 1
                print(f"Updated: {text} -> {clean_text}")
    print(f"Fixed {updated} entities.")

asyncio.run(fix_db())
