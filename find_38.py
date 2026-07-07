from pathlib import Path
from services.backend.infrastructure.cad.dxf_parser import DXFParser

parser = DXFParser()
for p in Path('i:/ai-2d-checker/storage/uploads/').glob('*.dxf'):
    try:
        entities, _, _, _ = parser.parse_file(p)
        for e in entities:
            text = e.get('properties', {}).get('text', '')
            if text and '38' in text:
                print(f"Found '38' in {p.name}")
                break
    except Exception as e:
        print(f"Error parsing {p.name}: {e}")
