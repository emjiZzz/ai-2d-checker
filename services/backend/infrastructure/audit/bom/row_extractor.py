from typing import List, Dict, Any
from ....domain.models.audit_violation import AuditViolation
from ....domain.models.extracted_entity import ExtractedEntity
from ....logger import logger
from .constants import ITEM_NO_PATTERN

def extract_bom_rows(entities: List[ExtractedEntity]) -> List[Dict[str, Any]]:
    """
    Scans all block inserts and text objects in the CAD metadata to reconstruct
    the Bill of Materials (BOM) tabular records.
    """
    bom_rows = []
    seen_items = set()

    for ent in entities:
        if ent.entity_type == "block" and ent.properties:
            attrs = ent.properties.get("attributes", {})
            if not attrs:
                continue

            # Locate the item number attribute tag
            item_no = None
            for tag in ("NO", "ITEM", "番号", "項目"):
                if tag in attrs and str(attrs[tag]).strip():
                    item_no = str(attrs[tag]).strip()
                    break

            if item_no and ITEM_NO_PATTERN.match(item_no):
                num = int(item_no)
                if num in seen_items:
                    continue
                seen_items.add(num)

                # Extract other row values
                part_name = ""
                for tag in ("NAME", "TITLE", "名称", "品名"):
                    if tag in attrs:
                        part_name = str(attrs[tag]).strip()
                        break

                part_no = ""
                for tag in ("PARTNO", "DWG", "図面番号", "型式", "MODEL"):
                    if tag in attrs:
                        part_no = str(attrs[tag]).strip()
                        break

                qty = "1"
                for tag in ("QTY", "個数", "数量"):
                    if tag in attrs:
                        qty = str(attrs[tag]).strip()
                        break

                bom_rows.append({
                    "item_no": num,
                    "part_name": part_name,
                    "part_number": part_no,
                    "quantity": qty,
                    "entity_id": str(ent.id),
                    "position": ent.geometry.get("insert", [0.0, 0.0])
                })

    # Fallback: scan text objects positioned in a vertical grid if no blocks were matched
    if not bom_rows:
        # Let's group text items that look like single numbers on standard BOM layers
        texts = [e for e in entities if e.entity_type == "text"]
        for txt in texts:
            val = (txt.properties.get("text") or txt.properties.get("value") or "").strip()
            if ITEM_NO_PATTERN.match(val) and txt.layer.lower() in ("am_bor", "border", "title", "bom"):
                num = int(val)
                if num not in seen_items:
                    seen_items.add(num)
                    bom_rows.append({
                        "item_no": num,
                        "part_name": "Extracted Text Item",
                        "part_number": "N/A",
                        "quantity": "1",
                        "entity_id": str(txt.id),
                        "position": txt.geometry.get("insert", [0.0, 0.0])
                    })

    return sorted(bom_rows, key=lambda r: r["item_no"])

def detect_balloons(entities: List[ExtractedEntity]) -> List[Dict[str, Any]]:
    """
    Locates visual balloon callouts.
    A balloon is defined as a circle with radius between 2.0 and 10.0 mm
    containing a numeric text annotation inside its coordinate space.
    """
    circles = [e for e in entities if e.entity_type == "circle"]
    texts = [e for e in entities if e.entity_type == "text"]
    balloons = []

    for circle in circles:
        geo = circle.geometry or {}
        center = geo.get("center")
        radius = geo.get("radius")
        if not center or radius is None:
            continue

        # Standard balloon scale limits
        if not (2.0 <= radius <= 10.0):
            continue

        cx, cy = center[0], center[1]

        # Look for number text matching the circle boundary
        for txt in texts:
            tgeo = txt.geometry or {}
            t_pos = tgeo.get("insert") or tgeo.get("location")
            if not t_pos:
                continue

            tx, ty = t_pos[0], t_pos[1]
            dist = ((tx - cx)**2 + (ty - cy)**2)**0.5
            if dist <= radius:
                val = (txt.properties.get("text") or txt.properties.get("value") or "").strip()
                if ITEM_NO_PATTERN.match(val):
                    balloons.append({
                        "item_no": int(val),
                        "center": [cx, cy],
                        "radius": radius,
                        "entity_id": str(circle.id)
                    })
                    break

    return balloons

def reconcile(
    bom_rows: List[Dict[str, Any]],
    balloons: List[Dict[str, Any]],
    audit_session_id: str
) -> List[AuditViolation]:
    """
    Performs comparative checks of BOM rows against drawing balloon tags.
    """
    violations = []
    bom_item_numbers = {r["item_no"] for r in bom_rows}
    balloon_item_numbers = {b["item_no"] for b in balloons}

    # 1. Detect orphan balloon callouts (Balloons with no BOM definition)
    orphan_items = balloon_item_numbers - bom_item_numbers
    for orphan in orphan_items:
        # Find coordinates of the orphan balloon
        balloon = next(b for b in balloons if b["item_no"] == orphan)
        violations.append(
            AuditViolation(
                audit_session_id=audit_session_id,
                severity="critical",
                category="bom_balloon_mismatch",
                description=f"Orphan balloon callout detected: Item callout '{orphan}' has no matching item definition in the Bill of Materials (BOM).",
                recommendation=f"Add a corresponding row for item #{orphan} to the BOM table, or delete the balloon markup.",
                source="rule_engine",
                confidence=1.0,
                affected_entities=[{"id": balloon["entity_id"], "type": "circle"}],
                coordinates=balloon["center"],
                standard_reference="ISO 6433 (Technical Drawings - Item References)"
            )
        )

    # 2. Detect unlinked BOM items (BOM row exists, but has no balloon pointer)
    unlinked_items = bom_item_numbers - balloon_item_numbers
    for unlinked in unlinked_items:
        row = next(r for r in bom_rows if r["item_no"] == unlinked)
        violations.append(
            AuditViolation(
                audit_session_id=audit_session_id,
                severity="high",
                category="bom_balloon_mismatch",
                description=f"Unlinked BOM row: Item definition #{unlinked} ('{row['part_name']}') is declared in the Bill of Materials but is missing a balloon pointer callout.",
                recommendation=f"Insert a standard balloon callout tag pointing to component #{unlinked} inside the primary layout views.",
                source="rule_engine",
                confidence=1.0,
                affected_entities=[{"id": row["entity_id"], "type": "block"}],
                coordinates=row["position"],
                standard_reference="ISO 6433 (Technical Drawings - Item References)"
            )
        )

    if violations:
        logger.info(f"BOM Reconciler complete: detected {len(violations)} reconciliation mismatches.")
    return violations
