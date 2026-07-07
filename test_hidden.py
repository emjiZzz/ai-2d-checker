import json
from pathlib import Path
from services.backend.infrastructure.cad.dxf_parser import DXFParser

parser = DXFParser()
entities, layers, counts, metadata = parser.parse_file(Path('i:/ai-2d-checker/storage/uploads/3346a8b4a97294124a69e89b056c7879226b782a25753deedcaea10adf055493.dxf'))

hidden_layers = set()
for l in layers:
    props = l.get("properties", {})
    if props.get("is_off") or props.get("is_frozen"):
        hidden_layers.add(l["layer"])

for e in entities:
    txt = e.get("properties", {}).get("text", "")
    if txt in ["68", "128", "178", "25", "M6通シ"]:
        layer = e.get("layer", "")
        is_hidden = layer in hidden_layers
        geom = e.get("geometry", {})
        print(f"TEXT: {txt}, LAYER: {layer}, HIDDEN: {is_hidden}, GEOM: {geom}")
