import re

async def detect_revision(entities: list[dict]) -> tuple[str | None, str | None]:
    part_number = None
    revision_letter = None

    REQUIRED_TITLE_PATTERNS = {
        "part_number": [r"dwg\.?\s*no", r"drawing\s*no", r"図面番号", r"部番", r"図番"],
        "revision_letter": [r"rev(?:\.?\s*letter|\.?\s*no)?", r"revision", r"改訂", r"版"]
    }

    # Search in block attributes
    for item in entities:
        if item.get("entity_type") == "block" and "properties" in item:
            attrs = item["properties"].get("attributes", {})
            for tag, val in attrs.items():
                if val:
                    tag_lower = tag.lower()
                    if not part_number and any(re.search(pat, tag_lower) for pat in REQUIRED_TITLE_PATTERNS["part_number"]):
                        if re.match(r'^[a-zA-Z0-9_-]{4,25}$', str(val).strip()):
                            part_number = str(val).strip().upper()
                    if not revision_letter and any(re.search(pat, tag_lower) for pat in REQUIRED_TITLE_PATTERNS["revision_letter"]):
                        if re.match(r'^[a-zA-Z0-9-]$', str(val).strip()):
                            revision_letter = str(val).strip().upper()

    # Search in general texts on title-block/border layers if blocks didn't resolve it
    if not part_number or not revision_letter:
        for item in entities:
            if item.get("entity_type") == "text" and "properties" in item:
                layer_lower = item.get("layer", "").lower()
                if any(l in layer_lower for l in ("am_bor", "border", "title", "title_block")):
                    props = item.get("properties") or {}
                    val = (props.get("text") or props.get("value") or "").strip()
                    if val:
                        val_lower = val.lower()
                        if not part_number:
                            for pat in REQUIRED_TITLE_PATTERNS["part_number"]:
                                match = re.search(f"{pat}\\s*[:：\\s]\\s*([a-zA-Z0-9_-]{{4,25}})", val_lower)
                                if match:
                                    part_number = match.group(1).upper()
                                    break
                        if not revision_letter:
                            for pat in REQUIRED_TITLE_PATTERNS["revision_letter"]:
                                match = re.search(f"{pat}\\s*[:：\\s]\\s*([a-zA-Z0-9-])", val_lower)
                                if match:
                                    revision_letter = match.group(1).upper()
                                    break
    return part_number, revision_letter
