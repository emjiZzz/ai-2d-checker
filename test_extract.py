import sys
import os

sys.path.insert(0, 'i:/ai-2d-checker/services/backend')

from infrastructure.cad.dxf_parser import DXFParser

def safe_decode(text):
    try:
        return text.encode('cp1252').decode('cp932')
    except Exception:
        pass
    return text

dxf = r'I:\ai-2d-checker\apps\desktop\public\uploads\CMB3370N01_MCCA5_old.dxf'
if not os.path.exists(dxf):
    # Try finding any CMB3370 dxf
    import glob
    files = glob.glob(r'i:\ai-2d-checker\**\CMB3370N01_MCCA5*.dxf', recursive=True)
    if files:
        dxf = files[0]

if os.path.exists(dxf):
    print(f"Testing on {dxf}")
    parser = DXFParser(dxf)
    ents = parser.get_all_entities()
    
    # Simple search
    for e in ents:
        txt = e.properties.get("text", "").strip()
        decoded = safe_decode(txt).strip()
        if "Q'ty" in txt or "Q'ty" in decoded or "総" in decoded:
            print(f"Found Label: {decoded} at X:{e.ins[0]}, Y:{e.ins[1]}")
        if txt == "2" or decoded == "2":
            print(f"Found 2 at X:{e.ins[0]}, Y:{e.ins[1]}")
        if txt == "21" or decoded == "21":
            print(f"Found 21 at X:{e.ins[0]}, Y:{e.ins[1]}")
else:
    print('File not found')
