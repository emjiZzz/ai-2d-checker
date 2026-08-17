import re
from typing import List, Dict, Any, Optional
from ...utils.text import COMPONENT_OF_DWG_NO_FIELDS, compare_values, is_component_of_dwg_no
from ..bom_analyzer import BOMAnalyzer
from ..bom.row_extractor import detect_balloons
from . import taxonomy

def is_empty_placeholder_remark(val: str) -> bool:
    if not val or val == "NONE":
        return True
    v = val.strip()
    v = re.sub(r'^[-\u2014\u2015\u2500\u30fc\s]*$', '', v)
    return len(v) == 0

def get_val_outer(row_dict, key_name):
    obj = row_dict.get(key_name, {})
    if isinstance(obj, dict):
        return obj.get("value", "NONE") or "NONE"
    return obj or "NONE"

def get_row_key_local(row):
    no_val = get_val_outer(row, "NO")
    if no_val == "NONE":
        return ""
    return no_val.strip()

def key_sort_fn_local(key_str):
    if key_str.startswith("_ref_idx_"):
        try:
            return (2, int(key_str.split("_")[-1]), key_str)
        except Exception:
            pass
    if key_str.startswith("_rev_idx_"):
        try:
            return (3, int(key_str.split("_")[-1]), key_str)
        except Exception:
            pass
    try:
        nums = re.findall(r'\d+', key_str)
        if nums:
            return (0, int(nums[0]), key_str)
    except Exception:
        pass
    return (1, 0, key_str)

def is_blank_spacer_local(row, is_assembly_drawing):
    if not row:
        return True
    if is_assembly_drawing:
        dwg = get_val_outer(row, "DWG_NO")
        title = get_val_outer(row, "TITLE")
        return dwg == "NONE" and title == "NONE"
    else:
        code = get_val_outer(row, "CODE")
        dim = get_val_outer(row, "DIMENSION")
        return code == "NONE" and dim == "NONE"

def sanitize_title_value(val):
    if val == "NONE" or not val:
        return val
    val = re.sub(
        r'^(\s*|drawn|designed|checked|approved'
        r'|mach\.?\s*code|unit\s*code'
        r'|job\s*no\.?|dwg\s*no\.'
        r'|scale)'
        r'[\s\t]*[:\-\]+[\s\t]*',
        '', val, flags=re.IGNORECASE
    )
    return val.strip()

def inject_title_block_markings(
    clean_markings: list,
    ref_title_fields: dict,
    rev_title_fields: dict,
    ref_entities: list,
    rev_entities: list,
    ref_title_bbox: tuple | None = None,
    rev_title_bbox: tuple | None = None,
) -> None:
    field_labels_map = {
        "QTY": " T. Q'ty (Total Quantity)",
        "CROSS REF NO": " Cross ref No.",
        "PREVIOUS DWG NO": " Previous Dwg. No.",
        "DESIGNED": " DESIGNED",
        "DRAWN": " DRAWN",
        "SCALE": " SCALE",
        # Was keyed "NAME" while extract_title_block returns "TITLE" -- the lookup missed on
        # every drawing, so the title read NONE vs NONE and no marking was ever emitted for it.
        # The title block's 名称 cell holds two ruled rows; each is compared on its own so a
        # change to one is not hidden by the other matching.
        "TITLE": " TITLE",
        "TITLE SUB": " TITLE (2nd line)",
        "DATE": " Y/M/D (Date of Creation)",
        "JOB NO": " Job No.",
        "STD NO": " Std. No.",
        "STANDARD": " Standard",
        "MACHINE CODE": " Mach. code /  Unit Code",
        # Just "DWG. No." — the label used to enumerate the cell's sub-headers
        # (" DWG. No. /  Machine Type /  Unit No. /  Part No. /   Branch"), which read as five
        # fields when it is one identifier split across ruled sub-cells. Those segments no longer
        # get checklist items of their own (COMPONENT_OF_DWG_NO_FIELDS), so advertising them here
        # would name rows the reviewer cannot find.
        "DWG NO": " DWG. No.",
        "REVISION CODE": " AMD. / Design Chg No."
    }

    # Sub-item taxonomy tag per field (docs/checklist-taxonomy-grouping-implementation-
    # plan.md). STD NO/STANDARD/DWG NO have no dedicated taxonomy feature (the user's own
    # field list doesn't name one) — left as OTHER rather than forced into a nearby-sounding
    # key. MACHINE CODE gained `machine_unit_code` on 2026-08-17, on the owner's request, and
    # it covers 機器記号 AND ユニット記号 as one item — see the note in taxonomy.py.
    title_feature_map = {
        "QTY": "quantity",
        "CROSS REF NO": "cross_reference_number",
        "PREVIOUS DWG NO": "previous_drawing_number",
        "DESIGNED": "designed",
        "DRAWN": "drawn",
        "SCALE": "scale",
        # Both 名称 rows group under machine_name: they are two rows of ONE field, and the
        # taxonomy's other title-block name key (line_name) is in DEFERRED_FEATURES, which the
        # frontend renders as "not yet supported" -- claiming it here would misreport the row.
        "TITLE": "machine_name",
        "TITLE SUB": "machine_name",
        "DATE": "creation_date",
        "JOB NO": "job_number",
        "MACHINE CODE": "machine_unit_code",
        "REVISION CODE": "revision_code",
    }

    def _dwg_no_of(fields: dict) -> str:
        obj = fields.get("DWG NO", {})
        return sanitize_title_value(obj.get("value", "NONE") if isinstance(obj, dict) else obj)

    ref_dwg_no, rev_dwg_no = _dwg_no_of(ref_title_fields), _dwg_no_of(rev_title_fields)

    for field_key, display_label in field_labels_map.items():
        orig_obj = ref_title_fields.get(field_key, {"value": "NONE", "coordinates": None})
        rev_obj = rev_title_fields.get(field_key, {"value": "NONE", "coordinates": None})

        orig_val = sanitize_title_value(orig_obj.get("value", "NONE") if isinstance(orig_obj, dict) else orig_obj)
        kmti_val = sanitize_title_value(rev_obj.get("value", "NONE") if isinstance(rev_obj, dict) else rev_obj)

        # A segment of the drawing number gets no card of its own — the DWG No. card already
        # carries it, and its own marker would land on the same ruled cell. Mirrors the row-level
        # suppression in build_title_block_table and shares its corroboration rule, so the card
        # list and the checklist table can never disagree about what was dropped.
        at = COMPONENT_OF_DWG_NO_FIELDS.get(field_key)
        if at and is_component_of_dwg_no(orig_val, ref_dwg_no, at) \
                and is_component_of_dwg_no(kmti_val, rev_dwg_no, at):
            continue

        kmti_coords = rev_obj.get("coordinates", None) if isinstance(rev_obj, dict) else None
        orig_coords = orig_obj.get("coordinates", None) if isinstance(orig_obj, dict) else None
        
        # Equivalence checking
        status_val = compare_values(orig_val, kmti_val)

        # Bilateral corroboration guard (generalized from the old MACHINE-CODE-only version).
        #
        # A title field read on one side but NONE on the other is far more often an EXTRACTION
        # MISS than a real edit — the title-block extractor is heuristic and scale-sensitive
        # (see docs/title-block-false-findings-implementation-plan.md and the OCR/UL vault
        # gotchas). If the value the extractor *did* read is actually present in the OTHER
        # drawing's title region, the field was mis-extracted, not removed/added → report
        # MATCHED, never a false REMOVED/ADDED. Mirrors the BOM guard in inject_bom_markings.
        #
        # match_level=2 (exact + clean substring, no fuzzy prefix) + region-scoping to the title
        # bbox keep a short value like "4" from spuriously matching a random dimension: a bare
        # presence check must PROVE the value is on the sheet, not merely coincide with it.
        #
        # For a SHORT value even level 2 is too loose, because its substring pass can land inside
        # a longer identifier -- a mis-extracted Previous Dwg. No. of "1" was corroborated against
        # the "1" in "M7452A1N01" and turned a bad read into a green tick. A handful of characters
        # occurring somewhere in the title block is not evidence of anything, so demand an exact
        # whole-string hit (level 1) and let genuinely one-sided short values stay reported. This
        # errs toward showing a finding rather than hiding one, which is the safe direction here.
        def _corroboration_match_level(value: str) -> int:
            return 1 if len(str(value).strip()) <= 3 else 2

        if status_val in ("ADDED", "REMOVED"):
            if orig_val == "NONE" and kmti_val != "NONE":
                recovered = BOMAnalyzer.find_drawing_text_coordinates(
                    ref_entities, kmti_val, category="title_block",
                    region_bbox=ref_title_bbox, match_level=_corroboration_match_level(kmti_val),
                )
                if recovered and recovered.get("coords"):
                    status_val = "MATCHED"
                    orig_coords = recovered["coords"]
            elif kmti_val == "NONE" and orig_val != "NONE":
                recovered = BOMAnalyzer.find_drawing_text_coordinates(
                    rev_entities, orig_val, category="title_block",
                    region_bbox=rev_title_bbox, match_level=_corroboration_match_level(orig_val),
                )
                if recovered and recovered.get("coords"):
                    status_val = "MATCHED"
                    kmti_coords = recovered["coords"]
        
        rev_val_raw = rev_obj.get("value", "") if isinstance(rev_obj, dict) else str(rev_obj)
        if kmti_val and kmti_val != "NONE" and kmti_val != sanitize_title_value(rev_val_raw):
            kmti_coords = None
            
        orig_val_raw = orig_obj.get("value", "") if isinstance(orig_obj, dict) else str(orig_obj)
        if orig_val and orig_val != "NONE" and orig_val != sanitize_title_value(orig_val_raw):
            orig_coords = None

        if kmti_coords is None and kmti_val and kmti_val != "NONE":
            exact_coords = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, kmti_val, category="title_block")
            if exact_coords and exact_coords.get("coords"):
                kmti_coords = exact_coords["coords"]
        if orig_coords is None and orig_val and orig_val != "NONE":
            exact_coords = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, orig_val, category="title_block")
            if exact_coords and exact_coords.get("coords"):
                orig_coords = exact_coords["coords"]

        if kmti_val != "NONE" or orig_val != "NONE":
            details_str = f"Title block {display_label.lstrip('- ')} checked: {orig_val} vs {kmti_val}"
            if status_val == "CHANGED" and ((":" in orig_val and "/" in kmti_val) or ("/" in orig_val and ":" in kmti_val)):
                details_str += " (Standardized based on Standard context provided)"
            marking_entry = {
                "text_content": kmti_val if kmti_val != "NONE" else orig_val,
                "status": status_val,
                "details": details_str,
                "category": "title_block",
                "feature": title_feature_map.get(field_key, taxonomy.OTHER_FEATURE_KEY),
                "original_value": orig_val if status_val == "CHANGED" else None
            }
            if kmti_coords is not None:
                marking_entry["coordinates"] = kmti_coords
            if orig_coords is not None:
                marking_entry["ref_coordinates"] = orig_coords
            clean_markings.append(marking_entry)

def inject_bom_markings(
    clean_markings: list,
    ref_bom_rows: list,
    rev_bom_rows: list,
    is_assembly_drawing: bool,
    ref_bom_bbox: Optional[tuple],
    rev_bom_bbox: Optional[tuple],
    ref_entities: list,
    rev_entities: list,
    used_ref_entities: set,
    used_rev_entities: set
) -> None:
    # Sub-item taxonomy tag per BOM column (docs/checklist-taxonomy-grouping-
    # implementation-plan.md). One flat map covers both assembly and parts column
    # sets since their col_keys don't collide in meaning (NO/QTY/REMARK are shared
    # concepts in both). DWG_NO/TITLE/CODE/DIMENSION have no dedicated taxonomy
    # feature for their exact meaning and fall to OTHER except CODE, which maps to
    # material_specification as the closest real match.
    bom_feature_map = {
        "NO": "numbering_arrangement",
        "QTY": "quantity",
        "REMARK": "remarks",
        "CODE": "material_specification",
        "MATERIAL_WEIGHT": "material_weight",
        "FINISHED_WEIGHT": "material_weight",
    }

    filtered_ref = [r for r in ref_bom_rows if not is_blank_spacer_local(r, is_assembly_drawing)]
    filtered_rev = [r for r in rev_bom_rows if not is_blank_spacer_local(r, is_assembly_drawing)]

    ref_bom_map = {}
    for idx, r in enumerate(filtered_ref):
        k = get_row_key_local(r)
        if not k:
            k = f"_ref_idx_{idx}"
        ref_bom_map[k] = r

    rev_bom_map = {}
    for idx, r in enumerate(filtered_rev):
        k = get_row_key_local(r)
        if not k:
            k = f"_rev_idx_{idx}"
        rev_bom_map[k] = r

    # Build global texts sets for Fallback Global Text String Check
    ref_bom_texts = set()
    for r in filtered_ref:
        for col_val_obj in r.values():
            val = col_val_obj.get("value", "NONE") if isinstance(col_val_obj, dict) else col_val_obj
            if val and val != "NONE" and len(val.strip()) > 1:
                ref_bom_texts.add(val.strip().lower())

    rev_bom_texts = set()
    for r in filtered_rev:
        for col_val_obj in r.values():
            val = col_val_obj.get("value", "NONE") if isinstance(col_val_obj, dict) else col_val_obj
            if val and val != "NONE" and len(val.strip()) > 1:
                rev_bom_texts.add(val.strip().lower())

    bom_keys = list(set(ref_bom_map.keys()).union(set(rev_bom_map.keys())))
    bom_keys.sort(key=key_sort_fn_local)

    for key in bom_keys:
        rev_row = rev_bom_map.get(key, {})
        ref_row = ref_bom_map.get(key, {})

        row_label = f"Unnumbered Row" if (key.startswith("_ref_idx_") or key.startswith("_rev_idx_")) else f"Item {key}"

        if is_assembly_drawing:
            bom_cols = [
                ("NO", "No."),
                ("DWG_NO", " / DWG No."),
                ("TITLE", " / TITLE"),
                ("QTY", "Q'ty"),
                ("REMARK", " / Remark")
            ]
        else:
            bom_cols = [
                ("NO", "No."),
                ("CODE", " / Code"),
                ("DIMENSION", "/ / Dimension"),
                ("QTY", " / Q'ty"),
                ("MATERIAL_WEIGHT", "Kg / Material Wt(kg)"),
                ("FINISHED_WEIGHT", "Kg / Finished Wt(kg)"),
                ("REMARK", " / Remark")
            ]

        # Non-MATCHED cells are collected here and emitted as ONE finding for the row.
        # The annotation guideline is explicit -- "A BOM row edited => 1 CHANGED per row, not
        # per cell" -- and the engine used to emit one per column, so a row where three cells
        # moved together produced three findings where a checker (and a human label) sees one.
        #
        # MATCHED cells are deliberately NOT collapsed. They are verification items in the
        # checklist, not findings; the guideline rule is about findings, and folding the
        # unchanged columns away would delete the per-column evidence a checker signs off on.
        #
        # The guideline's escape hatch -- "unless two cells changed for unrelated reasons" --
        # stays a HUMAN judgement. Do not try to detect it here: the engine has no way to tell
        # one semantic edit from two coincident ones, and guessing would put an unauditable
        # split back into the number this collapse exists to make honest.
        changed_cells: list[dict] = []

        for col_key, display_label in bom_cols:
            rev_cell = rev_row.get(col_key, {"value": "NONE", "coordinates": None})
            orig_cell = ref_row.get(col_key, {"value": "NONE", "coordinates": None})

            orig_val = orig_cell.get("value", "NONE") if isinstance(orig_cell, dict) else orig_cell
            kmti_val = rev_cell.get("value", "NONE") if isinstance(rev_cell, dict) else rev_cell
            kmti_coords = rev_cell.get("coordinates", None) if isinstance(rev_cell, dict) else None
            orig_coords = orig_cell.get("coordinates", None) if isinstance(orig_cell, dict) else None

            status_val = compare_values(orig_val, kmti_val)

            # Remarks Column Noise-Canceling
            if col_key == "REMARK":
                if is_empty_placeholder_remark(orig_val) and is_empty_placeholder_remark(kmti_val):
                    status_val = "MATCHED"

            # Safeguard 1: if the item number/row exists in both drawings, it is a change, never an addition or removal!
            if ref_row and rev_row and status_val in ("ADDED", "REMOVED"):
                status_val = "CHANGED"

            # Safeguard 2: Fallback Global Text String Check
            if status_val == "ADDED" and kmti_val.strip().lower() in ref_bom_texts:
                status_val = "MATCHED"
            elif status_val == "REMOVED" and orig_val.strip().lower() in rev_bom_texts:
                status_val = "MATCHED"
            elif status_val == "CHANGED":
                if kmti_val.strip().lower() in ref_bom_texts and orig_val.strip().lower() in rev_bom_texts:
                    status_val = "MATCHED"

            # Fix B3 Exact value coordinate lookup, spatially constrained to BOM bbox.
            if kmti_coords is None and kmti_val and kmti_val != "NONE":
                exact_coords = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, kmti_val, category="bill_of_materials", region_bbox=rev_bom_bbox, used_entities=used_rev_entities)
                if exact_coords and exact_coords.get("coords"):
                    ec = exact_coords["coords"]
                    if rev_bom_bbox and not (rev_bom_bbox[0] <= ec[0] <= rev_bom_bbox[2] and rev_bom_bbox[1] <= ec[1] <= rev_bom_bbox[3]):
                        ec = None
                    if ec:
                        kmti_coords = ec
            if orig_coords is None and orig_val and orig_val != "NONE":
                exact_coords = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, orig_val, category="bill_of_materials", region_bbox=ref_bom_bbox, used_entities=used_ref_entities)
                if exact_coords and exact_coords.get("coords"):
                    ec = exact_coords["coords"]
                    if ref_bom_bbox and not (ref_bom_bbox[0] <= ec[0] <= ref_bom_bbox[2] and ref_bom_bbox[1] <= ec[1] <= ref_bom_bbox[3]):
                        ec = None
                    if ec:
                        orig_coords = ec

            if kmti_val != "NONE" or orig_val != "NONE":
                details_str = f"BOM [{row_label}] {display_label} checked: {orig_val} vs {kmti_val}"
                if status_val == "CHANGED" and col_key in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
                    try:
                        if float(orig_val) == float(kmti_val) and re.search(r'\.\d{2}$', kmti_val.strip()):
                            status_val = "MATCHED"
                            details_str = f"BOM [{row_label}] {display_label} matched: {orig_val} vs {kmti_val} (Standardized to 2 decimals)"
                    except ValueError:
                        pass

                marking_entry = {
                    "text_content": kmti_val if kmti_val != "NONE" else orig_val,
                    "status": status_val,
                    "details": details_str,
                    "category": "bill_of_materials",
                    "feature": bom_feature_map.get(col_key, taxonomy.OTHER_FEATURE_KEY),
                    "original_value": orig_val if status_val == "CHANGED" else None
                }
                if kmti_coords is not None:
                    marking_entry["coordinates"] = kmti_coords
                if orig_coords is not None:
                    marking_entry["ref_coordinates"] = orig_coords

                # Spatial boundary filter (Stray BOM marker over Title Block area).
                # Stays per-CELL and ahead of the collapse: it is a judgement about where one
                # cell's glyph landed, so a stray cell must drop out before it can contribute
                # its coordinates to a row-level finding.
                if kmti_coords is not None and kmti_coords[1] < 60.0:
                    continue

                if status_val == "MATCHED":
                    clean_markings.append(marking_entry)
                else:
                    marking_entry["_display_label"] = display_label
                    marking_entry["_orig_val"] = orig_val
                    marking_entry["_kmti_val"] = kmti_val
                    changed_cells.append(marking_entry)

        # One finding per row. Anchored on the FIRST changed cell in `bom_cols` order -- a
        # deterministic anchor, matching the convention the guideline already uses for bulk
        # findings, so the same edit always reports at the same place.
        if changed_cells:
            anchor = changed_cells[0]
            statuses = {c["status"] for c in changed_cells}
            # Uniform when the whole row moved one way (Safeguard 1 already forces ADDED/
            # REMOVED to CHANGED whenever both rows exist, so a mix means the row genuinely
            # both gained and lost content -- which is a change).
            row_status = statuses.pop() if len(statuses) == 1 else "CHANGED"

            if len(changed_cells) == 1:
                # Single-cell rows keep today's exact wording, so the common case is
                # byte-identical to the pre-collapse engine and the diff is auditable.
                details_str = anchor["details"]
            else:
                parts = "; ".join(
                    f"{c['_display_label']} {c['_orig_val']} vs {c['_kmti_val']}"
                    for c in changed_cells
                )
                details_str = (
                    f"BOM [{row_label}] {len(changed_cells)} columns changed: {parts}"
                )

            row_entry = {
                "text_content": anchor["text_content"],
                "status": row_status,
                "details": details_str,
                "category": "bill_of_materials",
                "feature": anchor["feature"],
                "original_value": anchor["original_value"] if row_status == "CHANGED" else None,
            }
            if "coordinates" in anchor:
                row_entry["coordinates"] = anchor["coordinates"]
            if "ref_coordinates" in anchor:
                row_entry["ref_coordinates"] = anchor["ref_coordinates"]

            clean_markings.append(row_entry)

def _bom_item_numbers(bom_rows: list) -> set:
    nums = set()
    for r in bom_rows:
        raw = get_val_outer(r, "NO")
        if raw == "NONE":
            continue
        m = re.search(r'\d+', raw)
        if m:
            nums.add(int(m.group()))
    return nums


def _bom_row_by_item_no(bom_rows: list) -> dict:
    by_num = {}
    for r in bom_rows:
        raw = get_val_outer(r, "NO")
        if raw == "NONE":
            continue
        m = re.search(r'\d+', raw)
        if m:
            by_num[int(m.group())] = r
    return by_num


def _bom_row_coords(row: dict):
    cell = row.get("NO") if isinstance(row, dict) else None
    if isinstance(cell, dict):
        return cell.get("coordinates")
    return None


def inject_ballooning_markings(
    clean_markings: list,
    ref_bom_rows: list,
    rev_bom_rows: list,
    ref_entities: list,
    rev_entities: list
) -> None:
    """
    Cross-checks each drawing's balloon callouts (circled item-number tags on the
    drawing views) against its own BOM row numbers, using row_extractor.py's
    detect_balloons() — real geometry-based detection, reused rather than
    reimplemented. Deliberately NOT the full 4-state orphan/unlinked/resolved audit
    that row_extractor.py::reconcile() runs for a single drawing: this pipeline
    compares REF vs REV, so only ballooning issues that are new in the revision
    (absent as an issue in the reference) are surfaced as markings here. An issue
    present in both drawings is a pre-existing condition, not a regression introduced
    by this revision, and is left to the separate standards-compliance audit path
    instead of being duplicated as a "finding" on every comparison.
    """
    ref_balloons = detect_balloons(ref_entities)
    rev_balloons = detect_balloons(rev_entities)

    ref_bom_nums = _bom_item_numbers(ref_bom_rows)
    rev_bom_nums = _bom_item_numbers(rev_bom_rows)

    ref_balloon_nums = {b["item_no"] for b in ref_balloons}
    rev_balloon_nums = {b["item_no"] for b in rev_balloons}

    ref_orphan = ref_balloon_nums - ref_bom_nums
    rev_orphan = rev_balloon_nums - rev_bom_nums
    ref_unlinked = ref_bom_nums - ref_balloon_nums
    rev_unlinked = rev_bom_nums - rev_balloon_nums

    new_orphan = rev_orphan - ref_orphan
    new_unlinked = rev_unlinked - ref_unlinked

    rev_balloon_by_num = {b["item_no"]: b for b in rev_balloons}
    rev_bom_by_num = _bom_row_by_item_no(rev_bom_rows)

    for item_no in sorted(new_orphan):
        balloon = rev_balloon_by_num.get(item_no)
        marking_entry = {
            "text_content": f"Balloon {item_no}",
            "status": "ADDED",
            "details": f"BOM ballooning: item #{item_no} has a balloon callout in the revision with no matching BOM row (not an issue in the reference).",
            "category": "bill_of_materials",
            "feature": "ballooning",
        }
        if balloon:
            marking_entry["coordinates"] = balloon["center"]
        clean_markings.append(marking_entry)

    for item_no in sorted(new_unlinked):
        row = rev_bom_by_num.get(item_no, {})
        coords = _bom_row_coords(row)
        marking_entry = {
            "text_content": f"Item {item_no}",
            "status": "ADDED",
            "details": f"BOM ballooning: item #{item_no} is listed in the revision's BOM with no balloon callout pointing to it in the drawing views (not an issue in the reference).",
            "category": "bill_of_materials",
            "feature": "ballooning",
        }
        if coords is not None:
            marking_entry["coordinates"] = coords
        clean_markings.append(marking_entry)


def generate_auto_matched_markings(
    clean_markings: list,
    rev_geom: str,
    rev_notes: str,
    rev_iso_text: str
) -> None:
    from .hallucination_guardrails import is_admin_bom_marking

    changed_or_removed_ids = set()
    for m in clean_markings:
        if m.get("entity_id"):
            changed_or_removed_ids.add(m.get("entity_id"))

    all_rev_formatted = rev_geom.split('\n') + rev_notes.split('\n')
    for line in all_rev_formatted:
        line = line.strip()
        if not line:
            continue
        
        match = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]\s*(.*)$', line)
        if match:
            entity_id = match.group(1).strip()
            text_content = match.group(2).strip()
            
            if entity_id not in changed_or_removed_ids:
                # Skip administrative/title block markers from being auto-matched
                if not is_admin_bom_marking({"text_content": text_content, "category": "drawing_views"}):
                    clean_markings.append({
                        "entity_id": entity_id,
                        "text_content": text_content,
                        "status": "MATCHED",
                        "details": "Element verified and matches reference.",
                        "category": "drawing_views"
                    })
