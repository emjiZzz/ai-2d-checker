import asyncio
from infrastructure.storage.mongo import get_database
from domain.models.extracted_entity import ExtractedEntity
from api.v1 import find_drawing_text_coordinates

async def test_find():
    await get_database()
    # KMTI drawing ID:
    # 66d194fd31ee90b69149c548d14412a0ec1dab32ed480971766c58842fdb88fa
    # Wait, ebeb2563... is the filename. We need drawing_id.
    from services.backend.domain.models.drawing import DrawingDocument
    docs = await DrawingDocument.find().to_list()
    kmti_doc = next(d for d in docs if 'ebeb2563' in d.file_path)
    entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == str(kmti_doc.id)).to_list()
    
    print("Testing 38...")
    res38 = find_drawing_text_coordinates(entities, "38", "drawing_views", None, set(), [])
    print("38:", res38)
    
    print("Testing 12...")
    res12 = find_drawing_text_coordinates(entities, "12", "drawing_views", None, set(), [])
    print("12:", res12)
    
    print("Testing 2-C1...")
    res2c1 = find_drawing_text_coordinates(entities, "2-c1", "drawing_views", None, set(), [])
    print("2-C1:", res2c1)

asyncio.run(test_find())
