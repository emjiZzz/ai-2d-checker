import re

ITEM_NO_PATTERN = re.compile(r'^\d{1,3}$')

ZONE_KEYWORDS = {
    "title": ["title", "scale", "drawn", "checked", "approved"],
    "bom": ["bom", "parts", "material", "partslist", "materials", "material wt", "仕上重量", "finished wt", "材質", "寸法"],
    "notes": ["note", "anno", "comment", "annotation", "text", "注記"],
    "iso": ["iso", "isometric", "3d"],
    "views": ["dim", "dimension", "callout", "geometry"],
    "tolerance": ["tolerance", "公差", "一般公差"]
}

def map_signature_value(text: str) -> str:
    """Helper to trim and standardise empty values to NONE."""
    if not text:
        return "NONE"
    return text.strip()
