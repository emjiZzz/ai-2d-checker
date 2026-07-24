"""
prompt_builder.py — Category and system prompt generation for Gemini Full-AI comparison.
"""

from typing import Any
from google.genai import types

from .....domain.models.drawing_document import DrawingDocument
from .....logger import logger
from ...context_builder import load_drawing_png


def build_drawing_views_prompt_instructions() -> str:
    return (
        "=== CATEGORY: DRAWING VIEWS (Senior Industrial CAD Auditor Persona - ISO 128 / JIS B 0001) ===\n"
        "Evaluate `drawing_views` across all orthogonal, detail, and section views.\n"
        "Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Must evaluate these 11 features strictly (feature keys in parentheses — use them verbatim as the `feature` value on any canvas_marking you tag under drawing_views, see the canvas_markings instructions below):\n"
        "1. Origin (origin): Evaluate datum reference lines (Base Datum Edge / Centerlines) and view origin placement. Do NOT output 'N/A' — report 'Datum Origin / Centerlines Aligned (Maintained)' if views match.\n"
        "2. Alignment of Views (alignment_of_views): Check orthographic projection alignment across front, top, side, and section views.\n"
        "3. Line Attributes (line_attributes): Check line types (hidden, center, solid, phantom, hatching).\n"
        "4. Dimensions (dimensions): Summarize dimensions broken down by drawing view (e.g. Main View: 140, 100, 15 | Section A-A: 170 +0/-0.1). Include dimensional fit tolerances.\n"
        "5. Hole Properties (hole_properties): Detail hole callouts, drill sizes (キリ), counterbores (ザグリ), and depth (深サ).\n"
        "6. Chamfer/Radius (chamfer_radius): Detail chamfers (C1, C2) and radii (R2, R3, R0.5), noting view additions (e.g., Reference: 2x R3, 1x R0.5 | Revision: R2, R4, R0.5 [Added Detail View]). Mark as CHANGED or ADDED as applicable.\n"
        "7. Machining Symbol (machining_symbol): Visually inspect the PNG renderings for surface-finish / machining marks (∇, √). This is a DIFFERENT symbol from Welding Symbol below — do not conflate the two.\n"
        "8. Welding Symbol (welding_symbol): Visually inspect the PNG renderings for graphical welding symbols (fillet △, bevel ∨). Extracted text takes precedence for numeric data; visual OCR takes precedence for graphical weld symbols.\n"
        "9. Geometric Tolerances (geometric_tolerances): Capture both GD&T feature control frames (⊕, ⊥, □) AND dimensional fit/limit tolerances (170 +0/-0.1, 15 +0/-0.05, ±0.02).\n"
        "10. Additional Views (additional_views): Report newly added or modified detail/section views (e.g., 油溝詳細 Oil groove detail).\n"
        "11. Text Attributes (text_attributes): Standard text font, height, and spacing.\n"
    )


def build_notes_prompt_instructions() -> str:
    return (
        "=== CATEGORY: NOTES SECTION ===\n"
        "Evaluate `notes_section` for standard notes, special manufacturing instructions, and heat treatment callouts.\n"
        "Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Evaluate: standard notes, special notes.\n"
    )


def build_title_block_prompt_instructions() -> str:
    return (
        "=== CATEGORY: TITLE BLOCK ===\n"
        "Evaluate `title_block` metadata. Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Must evaluate these 10 features (feature keys in parentheses — use them verbatim as the `feature` value on any canvas_marking you tag under title_block):\n"
        "1. Machine Name (machine_name): the product/machine title text.\n"
        "2. Line Name (line_name): there is no reliable signal for this field in these drawings — mark it 'N/A' / MATCHED rather than guessing at a value.\n"
        "3. Scale (scale)\n"
        "4. Designed (designed): the 'designed by' signee/date field.\n"
        "5. Drawn (drawn): the 'drawn by' signee/date field.\n"
        "6. Quantity (quantity)\n"
        "7. Job Number (job_number)\n"
        "8. Cross Reference Number (cross_reference_number)\n"
        "9. Previous Drawing Number (previous_drawing_number)\n"
        "10. Revision Code (revision_code): the amendment/correction mark, often labeled AMD. or 訂正符号 — mark 'N/A' / MATCHED if the drawing has no revision-code field at all rather than inventing one.\n"
    )


def build_isometric_prompt_instructions() -> str:
    return (
        "=== CATEGORY: ISOMETRIC VIEW ===\n"
        "Evaluate `isometric_view` (3D perspective representations usually placed in the corner).\n"
        "IMPORTANT: Isometric views often lack text labels in CAD context. Visually inspect the PNG renderings to verify if a 3D perspective representation exists before concluding it is missing.\n"
        "Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Evaluate: orientation, scale, location.\n"
    )


def build_others_prompt_instructions() -> str:
    return (
        "=== CATEGORY: OTHER ENGINEERING REFERENCES ===\n"
        "Evaluate `other_engineering_references`. Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Evaluate these 2 features (feature keys in parentheses): Tree View Properties / Link (tree_view_properties), Excel — Additional Information (excel_additional_info).\n"
    )


def build_categorization_discipline_instructions() -> str:
    return (
        "=== CATEGORIZATION DISCIPLINE (apply this before evaluating any category below) ===\n"
        "The six categories are mutually exclusive. Every annotation, dimension, or data item "
        "belongs to exactly ONE of them, based on where it physically is on the sheet and what "
        "it represents — never based on which category section you happen to be writing about.\n"
        "- `title_block`: ONLY the metadata block(s) — typically a bottom-right stamp (title, "
        "drawing number, scale, drawn/designed/checked/approved by, date) and/or a secondary "
        "upper-left admin block (unit no., part no., quantity, stock qty).\n"
        "- `bill_of_materials`: ONLY the parts/materials schedule table (item no., code, "
        "dimension, quantity, weight, material, remarks), including Shim Tables (`シム表` / Shim Schedule).\n"
        "- `isometric_view`: ONLY the 3D perspective representation, usually in its own "
        "dedicated box in a corner of the sheet.\n"
        "- `notes_section`: ONLY free-text manufacturing/process instructions and callouts "
        "(e.g. \"Tap and drill holes to be chamfered\") — not dimensions, not title block data.\n"
        "- `drawing_views`: the orthogonal/section/detail views and their dimensions, "
        "tolerances, hole callouts, and geometry — everything that is NOT part of the title "
        "block, BOM, isometric box, or notes text. Do not report a title block field, BOM row, "
        "or notes entry here just because it sits spatially near a view.\n"
        "- `other_engineering_references`: anything else (tree view properties, external "
        "links, Excel data) that doesn't fit the five categories above.\n"
        "SHIM TABLE EXCLUSION RULE: Shim Tables (`シム表` / Shim Schedule listing thickness `t`, material, quantity, `設計組厚サ`, `総厚サ`) "
        "are auxiliary reference schedules and are EXPLICITLY OUT OF SCOPE for comparison. "
        "DO NOT generate any canvas_markings or table entries for Shim Tables — ignore their contents completely and do nothing with them.\n"
        "If uncertain whether something is a title block field, BOM row, or notes entry versus "
        "a drawing_views annotation, prefer the more specific category over the catch-all "
        "drawing_views.\n"
    )


def format_subview_breakdown(subviews: list, prefix: str) -> str:
    """Render detect_subviews() output as grounding text for the drawing_views prompt."""
    if not subviews:
        return f"{prefix}: No distinct sub-views detected — treat as a single Main View."
    lines = [f"{prefix}: {len(subviews)} sub-view(s) detected via deterministic anchor clustering:"]
    for sv in subviews:
        bbox = tuple(round(c, 1) for c in sv["bbox"])
        lines.append(f"  - \"{sv['label']}\" — bbox={bbox}")
    return "\n".join(lines)


def build_full_system_instruction() -> str:
    header = (
        "You are a Senior Industrial CAD Engineering Auditor performing a rigorous comparison between a REFERENCE drawing and a REVISION drawing.\n"
        "For each category (except bill_of_materials which uses its own format), you MUST provide a markdown table in `reference_content` with exactly 4 columns: `Feature | Original Value | Revision Value | Status`.\n"
        "CRITICAL: If a feature is not present in either drawing, mark it N/A / MATCHED in the table rather than omitting the row or inventing content.\n"
        "For each category, determine the overall status (MATCHED, CHANGED, ADDED, REMOVED, or MISSING), write a detailed summary report in `difference_summary`, output the 4-column table in `reference_content`, and write a professional suggestion in `engineering_discrepancy_details`.\n"
    )
    markings_instr = (
        "For canvas_markings, produce one entry per significant annotation or data item found in the drawings — including BOTH MATCHED items AND changed/added/removed ones.\n"
        "For MATCHED items: set status='MATCHED', use EXACT text string, and populate category.\n"
        "Produce at least one MATCHED canvas_marking per MATCHED category so each verified item gets a green checkmark on the drawing canvas.\n"
        "CRITICAL — mark VALUES, not labels: for title_block and bill_of_materials specifically, a canvas_marking must point at the actual DATA VALUE (e.g. the text \"45\", \"ZHR\", \"1/2\"), never at the static field-name LABEL next to it (e.g. \"Unit No.\", \"DRAWN\", \"SCALE\"). Field labels are template boilerplate — do not emit a canvas_marking for one just because it also appears unchanged in both drawings.\n"
        "Assign `category` strictly per the CATEGORIZATION DISCIPLINE section above — do not tag a title block field, BOM row, or notes entry as `drawing_views` just because it is spatially near a view.\n"
        "Assign a `feature` sub-item tag to every canvas_marking, using the feature key (the snake_case name in parentheses in each category's section above) that best matches what it is:\n"
        "  - drawing_views: origin, alignment_of_views, line_attributes, dimensions, hole_properties, chamfer_radius, machining_symbol, welding_symbol, geometric_tolerances, additional_views, text_attributes\n"
        "  - notes_section: standard_notes, special_notes\n"
        "  - bill_of_materials: material_type, material_specification, quantity, material_weight, ballooning, remarks, numbering_arrangement\n"
        "  - title_block: machine_name, line_name, scale, designed, drawn, quantity, job_number, cross_reference_number, previous_drawing_number, revision_code\n"
        "  - isometric_view: orientation, scale, location\n"
        "  - other_engineering_references: tree_view_properties, excel_additional_info\n"
        "If nothing in a category's list confidently matches, set feature='other' rather than guessing — never invent a feature key not listed above.\n"
        "IMPORTANT: Provide 'visual_bbox' [ymin, xmin, ymax, xmax] normalized 0-1000 for each canvas_marking.\n"
    )
    return "\n\n".join([
        header,
        build_categorization_discipline_instructions(),
        build_drawing_views_prompt_instructions(),
        build_notes_prompt_instructions(),
        build_title_block_prompt_instructions(),
        build_isometric_prompt_instructions(),
        build_others_prompt_instructions(),
        markings_instr
    ])


def build_multimodal_contents(
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    prompt_text: str
) -> list[Any]:
    """
    Constructs the Gemini multimodal input tuple containing reference/revision PNGs and text.
    """
    ref_png = load_drawing_png(str(ref_drawing.id))
    rev_png = load_drawing_png(str(rev_drawing.id))

    contents: list[Any] = []
    if ref_png:
        contents.append("The following image is the REFERENCE (old) drawing:")
        contents.append(types.Part.from_bytes(data=ref_png, mime_type="image/png"))
    else:
        logger.warning(f"[full_ai] No PNG for reference drawing {ref_drawing.id} — text-only")

    if rev_png:
        contents.append("The following image is the REVISION (new) drawing:")
        contents.append(types.Part.from_bytes(data=rev_png, mime_type="image/png"))
    else:
        logger.warning(f"[full_ai] No PNG for revision drawing {rev_drawing.id} — text-only")

    contents.append(prompt_text)
    return contents
