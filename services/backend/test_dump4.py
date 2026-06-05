import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient

# Setup path so imports work cleanly without relative import issues if possible
# Actually, let's just copy the exact logic here so we don't need imports.
def safe_decode(s):
    try:
        return s.encode('cp1252').decode('cp932')
    except:
        return s

async def test():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['ai_2d_checker']
    # Use LDT11016U01_I_MMU_old.dxf's drawing ID if possible, but we just want the entities.
    # Let's get entities where we can find "Unit No."
    entities = await db['extracted_entities'].find({}).to_list(length=50000)
    
    structural_coords = []
    for e in entities:
        if e.get("entity_type") == "text":
            raw = e.get("properties", {}).get("text")
            if raw:
                dec = safe_decode(str(raw)).lower().strip()
                if any(kw in dec for kw in ["unit no", "ユニットno", "part no", "コードno", "stock q'ty", "在庫棚入庫", "t. q'ty", "総製作個数"]):
                    ins = e.get("geometry", {}).get("insert")
                    if ins and len(ins) >= 2:
                        structural_coords.append((ins[0], ins[1]))
                        print(f"FOUND LABEL: {repr(dec)} at {ins[0], ins[1]}")

    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for e in entities:
        if e.get("entity_type") == "text":
            ins = e.get("geometry", {}).get("insert")
            if ins and len(ins) >= 2:
                min_x = min(min_x, ins[0])
                max_x = max(max_x, ins[0])
                min_y = min(min_y, ins[1])
                max_y = max(max_y, ins[1])
                
    width = max_x - min_x if max_x > min_x else 1000.0
    height = max_y - min_y if max_y > min_y else 1000.0
    dx_margin = width * 0.04
    dy_margin = height * 0.04

    print(f"BBOX: {min_x}, {max_x}, {min_y}, {max_y} | W:{width} H:{height}")

    for e in entities:
        if e.get("entity_type") != "text":
            continue
        
        raw_txt = e.get("properties", {}).get("text")
        if raw_txt is None:
            continue
        text_val = safe_decode(str(raw_txt)).strip()
        if not text_val:
            continue
            
        text_lower = text_val.lower().strip()
        
        is_structural_value = False
        ins = e.get("geometry", {}).get("insert")
        if text_lower in ["11", "016", "1", "a"]:
            print(f"CHECKING TEXT: {repr(text_lower)} at {ins}")
            
            if ins and len(ins) >= 2:
                for cx, cy in structural_coords:
                    dy_diff = abs(ins[1] - cy)
                    dx_diff = abs(ins[0] - cx)
                    # Same row (Y-alignment) within 5% of drawing height, and physically to the right (or nearby)
                    if dy_diff < max(100.0, height * 0.05):
                        if dx_diff < max(1500.0, width * 0.6):
                            is_structural_value = True
                            print(f"  -> MARKED AS STRUCTURAL VALUE! dy_diff={dy_diff}, dx_diff={dx_diff}")
                            break
                    else:
                        print(f"  -> Failed Structural: dy_diff={dy_diff} vs {max(100.0, height * 0.05)}")

asyncio.run(test())
