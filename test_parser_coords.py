from pathlib import Path
from services.backend.infrastructure.cad.dxf_parser import DXFParser

parser = DXFParser()
entities, layers, counts, metadata = parser.parse_file(Path('i:/ai-2d-checker/storage/uploads/3346a8b4a97294124a69e89b056c7879226b782a25753deedcaea10adf055493.dxf'))

for e in entities:
    if e["entity_type"] == "dimension":
        geom = e.get("geometry", {})
        if "text_point" in geom:
            print(f"DIMENSION TEXT_POINT: {geom['text_point']}")
