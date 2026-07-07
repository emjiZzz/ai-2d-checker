import re

ITEM_NO_PATTERN = re.compile(r'^\d{1,3}$')

def map_signature_value(text: str) -> str:
    """Helper to trim and standardise empty values to NONE."""
    if not text:
        return "NONE"
    return text.strip()
