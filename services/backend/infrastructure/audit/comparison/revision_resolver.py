import re

def resolve_revisions(
    ref_entities: list,
    rev_entities: list,
    ref_file_hash: str,
    rev_file_hash: str,
    ref_file_name: str,
    rev_file_name: str
) -> tuple[str, str, str, str]:
    """Resolves drawing titles and revision letters from drawing entities and hashes."""
    ref_rev = "A"
    for e in ref_entities:
        if getattr(e, "entity_type", "") == "text":
            raw_txt = e.properties.get("text") if getattr(e, "properties", None) else None
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                m = re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', txt, re.IGNORECASE)
                if m:
                    ref_rev = m.group(1)
                    
    rev_rev = "B"
    for e in rev_entities:
        if getattr(e, "entity_type", "") == "text":
            raw_txt = e.properties.get("text") if getattr(e, "properties", None) else None
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                m = re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', txt, re.IGNORECASE)
                if m:
                    rev_rev = m.group(1)
    
    if ref_rev == rev_rev and ref_file_hash != rev_file_hash:
        try:
            ref_rev_char = ref_rev[0] if ref_rev else "A"
            rev_rev = chr(ord(ref_rev_char) + 1) if (ref_rev_char.isalpha() and len(ref_rev_char) == 1) else "B"
        except Exception:
            rev_rev = "B"

    ref_title = ref_file_name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').upper()
    rev_title = rev_file_name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').upper()

    return ref_rev, rev_rev, ref_title, rev_title
