# AI-2D-Checker: Comprehensive Implementation Plan
## "Aligning with Real-Life Engineering Drawing Checking"

> **Philosophy**: Every phase delivers real, measurable value. Later phases build on earlier ones.
> No phase should be skipped — each one closes a specific gap identified in the engineering workflow.

---

## Phase Overview

| Phase | Name | Focus | Priority |
|---|---|---|---|
| **Phase 1** | Foundation Repair | Fix critical broken wiring | 🔴 Critical |
| **Phase 2** | Rule Engine Expansion | 25+ deterministic checks | 🔴 Critical |
| **Phase 3** | Visual AI Grounding | Feed PNG to Gemini Vision | 🔴 Critical |
| **Phase 4** | Entity Extraction Enhancement | HATCH, LEADER, SPLINE, XREF | 🟠 High |
| **Phase 5** | BOM & Balloon Intelligence | Full BOM reconciliation | 🟠 High |
| **Phase 6** | Semantic RAG Completion | True vector search pipeline | 🟠 High |
| **Phase 7** | Revision Intelligence | Rev A → Rev B chain | 🟡 Medium |
| **Phase 8** | Engineer Feedback Loop | AI learns from corrections | 🟡 Medium |
| **Phase 9** | Advanced Reporting | Visual annotations, dashboards | 🟡 Medium |
| **Phase 10** | Enterprise Hardening | Batch audit, mobile, production | 🟢 Future |

---

---

# 🔴 PHASE 1: Foundation Repair
### Objective: Fix 4 broken critical wiring issues that prevent the core feature from working

**Duration estimate**: 1–2 weeks
**Risk**: Low (isolated changes, no architectural redesign)

---

## 1.1 — Wire PNG Rendering Into Gemini Vision API

**Problem**: `AIEngine.audit_drawing()` sends only JSON text to Gemini. The PNG rendering pipeline exists but is never connected to the AI call.

**Files to modify**:
- `services/backend/infrastructure/audit/ai_engine.py`
- `services/backend/infrastructure/rendering/viewport_generator.py`

**Implementation**:

```python
# In AIEngine.audit_drawing(), before the Gemini API call:

# Step 1: Render the drawing to a high-fidelity PNG
from ..rendering.viewport_generator import ViewportGenerator
png_bytes: bytes | None = None
try:
    png_bytes = await asyncio.to_thread(
        ViewportGenerator.render_to_bytes, drawing_id
    )
    logger.info(f"Drawing PNG rendered: {len(png_bytes)} bytes for Gemini Vision.")
except Exception as render_err:
    logger.warning(f"PNG render failed (non-fatal, continuing text-only): {render_err}")

# Step 2: Build multipart Gemini content
from google.genai import types as genai_types

content_parts = []
if png_bytes:
    content_parts.append(
        genai_types.Part.from_bytes(data=png_bytes, mime_type="image/png")
    )
content_parts.append(genai_types.Part.from_text(full_prompt))

# Step 3: Submit with vision
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=content_parts,
    config=genai_types.GenerateContentConfig(
        response_mime_type="application/json"
    )
)
```

**Expected improvement**: AI violation detection accuracy +200–300%. Gemini can now see the actual drawing layout, missing views, spatial relationships, and visual patterns.

---

## 1.2 — Wire Standards Ingestion to Vector Store

**Problem**: `StandardsLoader.ingest_standard()` saves chunks to MongoDB but never writes vectors to `index_shards.json`. RAG runs on regex, not semantics.

**Files to modify**:
- `services/backend/infrastructure/audit/standards_loader.py`

**Implementation**:

```python
# At the end of StandardsLoader.ingest_standard(), after saving db_chunks:

# Write chunk embeddings to local vector index
try:
    from ..ai.vectorstore.embedding_provider import EmbeddingProvider
    from ..ai.vectorstore.lancedb_manager import LanceDBManager

    provider = EmbeddingProvider()
    db_manager = LanceDBManager()

    texts = [c["content"] for c in chunks]
    vectors = provider.embed_texts(texts)

    records = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        records.append({
            "vector": vec,
            "text": chunk["content"],
            "metadata": {
                "standard_id": str(doc.id),
                "standard_hash": standard_hash,
                "section_header": chunk["section_header"],
                "chunk_index": i,
                "page_number": chunk["metadata"].get("page_number", 1)
            }
        })

    db_manager.write_embeddings("standards_reference", records)
    logger.info(f"Wrote {len(records)} vectors to local semantic index for standard '{name}'.")

except Exception as vec_err:
    logger.warning(f"Vector indexing failed (non-fatal): {vec_err}")
```

**Expected improvement**: RAG now uses true cosine-similarity semantic search. When auditing a drawing about "hole tolerances", it retrieves the correct ISO 286 clause — not a random keyword match.

---

## 1.3 — Add Copilot Stream Endpoint

**Problem**: The React Copilot panel calls `/api/v1/copilot/stream`. This route does not exist. Every user gets a silent 404.

**Files to modify**:
- `services/backend/api/v1.py`

**Implementation**:

```python
# Add to v1.py — after existing auth routes:

from fastapi.responses import StreamingResponse
from ..infrastructure.ai.copilot.streaming_engine import StreamingEngine
from ..infrastructure.ai.copilot.prompt_guardrails import PromptGuardrails

class CopilotStreamRequest(BaseModel):
    message: str
    context: str = ""
    history: list[dict] = []

@router.post(
    "/copilot/stream",
    summary="Stream AI Copilot response tokens via SSE",
    dependencies=[Depends(get_auth_token)]
)
async def copilot_stream(
    body: CopilotStreamRequest,
    session_token: str = Depends(get_session_token)
):
    """
    Streams token-by-token AI engineering assistant responses.
    Uses Gemini 2.0 Flash with engineering drawing context injection.
    Returns Server-Sent Events (SSE) chunked response.
    """
    # Input sanitization — block prompt injection
    if not PromptGuardrails.sanitize_input(body.message):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message contains disallowed content patterns."
        )

    # Combine history into full context prompt
    history_text = ""
    for turn in body.history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        history_text += f"\n[{role.upper()}]: {content}"

    full_prompt = f"{history_text}\n[USER]: {body.message}"

    async def sse_generator():
        async for token in StreamingEngine.generate_token_stream(
            prompt=full_prompt,
            context=body.context
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
```

---

## 1.4 — Persist Physical Comparison Results as AuditViolations

**Problem**: `perform_physical_comparison()` returns findings in the API response but never saves them. History is lost.

**Files to modify**:
- `services/backend/api/v1.py` (in `perform_physical_comparison` handler)
- `services/backend/domain/models/audit_session.py` (add `comparison_source` field)

**Implementation**:

```python
# After building the comparison response, persist canvas_markings as violations:

session = AuditSession(
    drawing_id=body.drawing_id,
    reference_drawing_id=body.reference_drawing_id,
    status="completed",
    compliance_score=_calc_comparison_score(response.canvas_markings),
    source="physical_comparison"
)
await session.save()

# Convert canvas_markings to AuditViolations
violations_to_save = []
for marking in response.canvas_markings:
    if marking.status in ("CHANGED", "ADDED", "REMOVED"):
        violations_to_save.append(AuditViolation(
            audit_session_id=str(session.id),
            severity="medium" if marking.status == "CHANGED" else "high",
            category=f"comparison_{marking.category}",
            description=marking.details,
            recommendation=f"Resolve discrepancy: '{marking.text_content}' differs from reference.",
            source="physical_comparison",
            confidence=0.95,
            affected_entities=[{"entity_id": marking.entity_id, "marker_shape": "BOX"}] if marking.entity_id else [],
            coordinates=marking.coordinates
        ))

if violations_to_save:
    await AuditViolation.insert_many(violations_to_save)
```

---

---

# 🔴 PHASE 2: Rule Engine Expansion
### Objective: Expand from 8 superficial rules to 25+ real engineering checks

**Duration estimate**: 2–3 weeks
**Files to modify**: `services/backend/infrastructure/audit/rule_engine.py`

---

## 2.1 — Title Block Completeness Checker

Real checkers verify all 10 title block fields are populated before releasing a drawing.

```python
# Rule: Title Block Field Completeness
REQUIRED_TITLE_FIELDS = {
    "SCALE": ["scale", "尺度"],
    "DWG_NO": ["dwg. no", "図面番号", "drawing number"],
    "TITLE": ["title", "名称"],
    "DESIGNED": ["designed", "設計"],
    "DRAWN": ["drawn", "作成"],
    "DATE": ["date", "日付"],
    "MATERIAL": ["material", "材質", "材料"],
    "REVISION": ["rev", "revision", "改訂"],
    "UNIT": ["unit", "単位"],
    "SHEET": ["sheet", "シート"],
}

title_block_texts = [
    e.properties.get("value", "").lower()
    for e in entities
    if e.layer.lower() in ("am_bor", "border", "title", "titleblock", "title_block")
]

found_fields = set()
for txt in title_block_texts:
    for field_key, keywords in REQUIRED_TITLE_FIELDS.items():
        if any(kw in txt for kw in keywords):
            found_fields.add(field_key)

missing_fields = set(REQUIRED_TITLE_FIELDS.keys()) - found_fields
if missing_fields:
    violations.append(AuditViolation(
        severity="high",
        category="incomplete_title_block",
        description=f"Title block is missing required fields: {', '.join(missing_fields)}",
        recommendation="Populate all mandatory title block fields before releasing for production.",
        standard_reference="ISO 7200 (Technical Drawings — Title Blocks)"
    ))
```

---

## 2.2 — GD&T Feature Control Frame Detector

```python
# Rule: GD&T symbols must follow valid format: |symbol|tolerance|datum|
# ezdxf extracts GD&T frames as TEXT/MTEXT entities containing special characters
GDT_SYMBOLS = {"⊙", "⊗", "◎", "⊘", "∥", "⊥", "∠", "⌖", "○", "□", "↗", "⌀"}

for txt in texts:
    val = txt.properties.get("value", "")
    if any(sym in val for sym in GDT_SYMBOLS):
        # Validate format: should contain a tolerance value
        has_tolerance_val = bool(re.search(r'\d+\.?\d*', val))
        has_datum = bool(re.search(r'[A-Z](?:\s*[A-Z])?$', val.strip()))

        if not has_tolerance_val:
            violations.append(AuditViolation(
                severity="high",
                category="malformed_gdt_frame",
                description=f"GD&T feature control frame '{val}' missing tolerance value.",
                recommendation="GD&T frames must follow format: [symbol][tolerance][datum ref]",
                standard_reference="ISO 1101 (GD&T — Geometrical Tolerancing)"
            ))
```

---

## 2.3 — Hole Callout Format Validator

```python
# Rule: Hole callouts must follow standard formats
# Valid: Ø6H7▽20, Ø12⌴5DEEP, M8×1.25THRU, Ø6.5✕90°
HOLE_CALLOUT_PATTERN = re.compile(
    r'[ØO∅]\s*\d+\.?\d*'  # Diameter symbol + value
    r'(?:[A-Z]\d+)?'       # Optional tolerance class (H7, f6, etc.)
    r'(?:▽\d+|DEEP\s*\d+|THRU)?',  # Optional depth/thru
    re.IGNORECASE
)

for txt in texts:
    val = txt.properties.get("value", "")
    if re.search(r'[ØO∅]', val):
        if not HOLE_CALLOUT_PATTERN.match(val.strip()):
            violations.append(AuditViolation(
                severity="medium",
                category="invalid_hole_callout",
                description=f"Hole callout '{val}' does not follow standard format.",
                recommendation="Use format: Ø[dia][tolerance class]▽[depth] or THRU.",
                standard_reference="ISO 129-1 (Dimensioning of Holes)"
            ))
```

---

## 2.4 — General Tolerance Declaration Checker

```python
# Rule: Every drawing must declare a general tolerance standard
TOLERANCE_STANDARDS = [
    "ISO 2768", "JIS B 0405", "ASME Y14.5",
    "DIN 7168", "一般公差", "GENERAL TOLERANCE"
]

all_text_values = [e.properties.get("value", "") for e in texts]
full_text_block = " ".join(all_text_values).upper()

has_tolerance_decl = any(std.upper() in full_text_block for std in TOLERANCE_STANDARDS)
if not has_tolerance_decl:
    violations.append(AuditViolation(
        severity="high",
        category="missing_general_tolerance_declaration",
        description="No general tolerance standard declared in drawing notes or title block.",
        recommendation="Add 'GENERAL TOLERANCES PER ISO 2768-m' or equivalent to the notes block.",
        standard_reference="ISO 2768 (General Tolerances)"
    ))
```

---

## 2.5 — Additional Rules to Implement in Phase 2

| Rule | Trigger Condition | Standard Reference |
|---|---|---|
| **Missing center lines** | Circle or arc exists, no dash-dot line in proximity | ISO 128-20 |
| **Projection type symbol** | No 1st/3rd angle projection icon block found | ISO 128-30 |
| **Text height non-standard** | Any text entity with height not in {2.5, 3.5, 5.0, 7.0} | ISO 3098 |
| **Dimension over-specification** | Same geometric distance dimensioned twice | ISO 129-1 |
| **Surface roughness missing** | Machined parts without Ra/Rz annotation | ISO 1302 |
| **Thread spec format** | Thread text not matching M#×pitch or UNC/UNF pattern | ISO 965 |
| **Missing section view arrows** | HATCH entity exists without leader/arrow pair | ISO 128-44 |
| **Scale mismatch** | Declared scale vs. actual geometry ratio differs > 5% | ISO 5455 |
| **Revision cloud missing** | Revision letter incremented but no revision cloud block | ISO 7573 |
| **Empty block attributes** | ATTRIB entity with empty tag value on production layer | ISO 7200 |

---

---

# 🔴 PHASE 3: Visual AI Grounding Enhancement
### Objective: Elevate the Gemini AI prompt quality from text-only to structured vision input

**Duration estimate**: 2–3 weeks
**Files to modify**: `services/backend/infrastructure/audit/ai_engine.py`

---

## 3.1 — Structured Context Pre-Processing

Instead of dumping a flat JSON of all entities into the prompt, pre-organize them into engineering-meaningful groups:

```python
def _build_structured_context(entities: list, drawing: DrawingDocument) -> dict:
    """
    Organizes raw entities into engineering-meaningful context blocks
    for dramatically improved Gemini reasoning quality.
    """
    return {
        "drawing_metadata": {
            "file_name": drawing.file_name,
            "format": drawing.format,
            "units": "Metric" if drawing.metadata.get("measurement") == 1 else "Imperial",
            "acad_version": drawing.metadata.get("acad_version"),
            "page_count": drawing.metadata.get("page_count", 1)
        },
        "title_block": {
            # Pre-extracted key-value pairs from title block layer
            "fields": _extract_title_block_fields(entities)
        },
        "layer_inventory": {
            "all_layers": list(set(e.layer for e in entities)),
            "active_layers": [l for l in set(e.layer for e in entities) if l != "0"],
            "has_dimension_layer": any("dim" in e.layer.lower() for e in entities),
            "has_notes_layer": any("note" in e.layer.lower() for e in entities),
        },
        "dimensions": {
            "count": len([e for e in entities if e.entity_type == "dimension"]),
            "values": [e.properties.get("text") for e in entities if e.entity_type == "dimension"],
            "types": [e.properties.get("dim_type") for e in entities if e.entity_type == "dimension"]
        },
        "annotations": {
            "notes_text": [e.properties.get("text") for e in entities
                          if e.entity_type == "text" and "note" in e.layer.lower()],
            "title_block_text": [e.properties.get("text") for e in entities
                                if e.layer.lower() in ("am_bor", "border", "title")]
        },
        "bom_rows": _extract_bom_structure(entities),
        "geometry_summary": {
            "line_count": len([e for e in entities if e.entity_type == "line"]),
            "circle_count": len([e for e in entities if e.entity_type == "circle"]),
            "arc_count": len([e for e in entities if e.entity_type == "arc"]),
            "hatch_count": len([e for e in entities if e.entity_type == "hatch"]),
            "block_count": len([e for e in entities if e.entity_type == "block"]),
        },
        "gdt_frames": _extract_gdt_frames(entities),
        "hole_callouts": _extract_hole_callouts(entities),
    }
```

---

## 3.2 — Dual-Pass AI Audit Strategy

Split the AI audit into two focused passes for higher precision:

**Pass 1 — Standards Compliance Check** (existing behavior, improved with image)
- Input: PNG image + structured context + RAG standard chunks
- Output: Standard violations (missing tolerances, wrong layers, etc.)

**Pass 2 — Visual Layout Check** (new)
- Input: PNG image + system prompt focused on visual layout only
- Output: Visual violations (missing views, crowded dimensions, unclear section cuts)

```python
# Pass 2 system instruction (visual-only)
visual_instruction = """
You are a senior engineering draftsman checking the VISUAL quality of this drawing.
Look at the image and identify:
1. Are all required views present? (Front, Top, Right, Section where needed)
2. Are dimension lines crossing geometry? (bad practice)
3. Are any drawing views incomplete or cut off?
4. Is there adequate spacing between dimensions?
5. Are section cut lines clearly indicated with arrows?
6. Are hatching patterns consistent within the same material?
7. Are any views missing center lines on circular features?

Return violations as structured JSON only.
"""
```

---

## 3.3 — Confidence Calibration Improvement

Current confidence scores are raw Gemini outputs (0–1). Add calibration based on:
- Grounding quality (how well the reference standard matches)
- Entity match quality (whether the violation maps to a real entity_id)
- Historical accuracy (track if engineers agree/disagree with AI findings)

```python
def _calibrate_confidence(raw: float, is_grounded: bool, has_entity: bool) -> float:
    score = raw
    if not is_grounded:
        score *= 0.5   # Penalize ungrounded references
    if not has_entity:
        score *= 0.8   # Penalize violations without entity anchors
    return max(0.1, min(1.0, score))
```

---

---

# 🟠 PHASE 4: Entity Extraction Enhancement
### Objective: Extract 6 additional entity types that real engineers read

**Duration estimate**: 2 weeks
**Files to modify**: `services/backend/infrastructure/cad/entity_mapper.py`, `dxf_parser.py`

---

## 4.1 — HATCH Entity Extraction (Section Cut Patterns)

Hatches identify cut sections, material zones, and filled regions. Without them, section view verification is impossible.

```python
@staticmethod
def map_hatch(entity: Any) -> dict[str, Any]:
    pattern_name = entity.dxf.pattern_name if hasattr(entity.dxf, "pattern_name") else "ANSI31"
    associative = entity.dxf.associativity if hasattr(entity.dxf, "associativity") else 0

    # Extract boundary paths (the enclosed area of the hatch)
    boundary_paths = []
    for path in entity.paths:
        if hasattr(path, "edges"):
            for edge in path.edges:
                if hasattr(edge, "start"):
                    boundary_paths.append([edge.start[0], edge.start[1]])

    return {
        "entity_type": "hatch",
        "layer": entity.dxf.layer,
        "properties": {
            "handle": entity.dxf.handle,
            "color": entity.dxf.color,
            "pattern_name": pattern_name,       # "ANSI31" = steel, "ANSI37" = cast iron, etc.
            "is_solid": entity.dxf.solid_fill,
            "associative": bool(associative)
        },
        "geometry": {
            "boundary_points": boundary_paths[:20]  # Limit for storage
        }
    }
```

---

## 4.2 — LEADER Entity Extraction (Note Pointers & Balloon Arrows)

Leaders connect annotation text to geometry. Critical for BOM balloon detection.

```python
@staticmethod
def map_leader(entity: Any) -> dict[str, Any]:
    vertices = []
    if hasattr(entity, "vertices"):
        for v in entity.vertices:
            vertices.append([v[0], v[1]])

    return {
        "entity_type": "leader",
        "layer": entity.dxf.layer,
        "properties": {
            "handle": entity.dxf.handle,
            "color": entity.dxf.color,
            "has_arrowhead": entity.dxf.arrowhead_flag if hasattr(entity.dxf, "arrowhead_flag") else 1,
        },
        "geometry": {
            "vertices": vertices,
            "tip": vertices[0] if vertices else None,   # Arrow tip (points to geometry)
            "tail": vertices[-1] if len(vertices) > 1 else None  # Text end
        }
    }
```

---

## 4.3 — TOLERANCE Entity Extraction (Stacked Fractions & GD&T Frames)

```python
@staticmethod
def map_tolerance(entity: Any) -> dict[str, Any]:
    """Maps TOLERANCE entities (GD&T feature control frames)."""
    insert = entity.dxf.insert if hasattr(entity.dxf, "insert") else [0, 0, 0]

    return {
        "entity_type": "tolerance",
        "layer": entity.dxf.layer,
        "properties": {
            "handle": entity.dxf.handle,
            "color": entity.dxf.color,
        },
        "geometry": {
            "insert": [insert[0], insert[1], insert[2]]
        }
    }
```

---

## 4.4 — XREF Detection (External Drawing References)

```python
# In DXFParser — detect external references
xrefs = []
for block in doc.blocks:
    if block.is_xref:
        xrefs.append({
            "entity_type": "xref",
            "layer": "0",
            "properties": {
                "name": block.name,
                "filename": block.block_record.dxf.xref_path,
                "is_resolved": not block.is_xref_unresolved
            },
            "geometry": {}
        })
```

---

---

# 🟠 PHASE 5: BOM & Balloon Intelligence
### Objective: Full bill-of-materials integrity verification — the #1 NCR cause in factories

**Duration estimate**: 3 weeks
**New file**: `services/backend/infrastructure/audit/bom_analyzer.py`

---

## 5.1 — BOM Table Extractor

Extract the BOM table from block attributes + text entities positioned in a grid pattern.

```python
class BOMAnalyzer:
    """
    Detects and extracts Bill of Materials tables from DXF entities.
    Reconciles balloon callouts against BOM item numbers.
    """

    # BOM row heuristic: look for numeric item numbers in blocks near the title block
    ITEM_NO_PATTERN = re.compile(r'^\d{1,3}$')
    QTY_PATTERN = re.compile(r'^\d{1,4}$')

    @staticmethod
    def extract_bom_rows(entities: list[ExtractedEntity]) -> list[dict]:
        """
        Groups block attributes into structured BOM rows.
        A BOM row consists of: Item No, Part Name/No, Qty, Material, Remarks.
        """
        bom_candidate_blocks = [
            e for e in entities
            if e.entity_type == "block"
            and e.properties.get("attributes")
        ]

        rows = []
        for block in bom_candidate_blocks:
            attrs = block.properties.get("attributes", {})
            # Detect BOM row pattern: must have an item number key
            item_no = attrs.get("NO", attrs.get("ITEM", attrs.get("番号", "")))
            if BOMAnalyzer.ITEM_NO_PATTERN.match(str(item_no).strip()):
                rows.append({
                    "item_no": int(item_no),
                    "part_name": attrs.get("NAME", attrs.get("名称", "")),
                    "part_number": attrs.get("PARTNO", attrs.get("DWG", attrs.get("図面番号", ""))),
                    "quantity": attrs.get("QTY", attrs.get("個数", "")),
                    "material": attrs.get("MATERIAL", attrs.get("材質", "")),
                    "remarks": attrs.get("REMARK", attrs.get("備考", "")),
                    "position": block.geometry.get("insert", [0, 0])
                })

        return sorted(rows, key=lambda r: r["item_no"])
```

---

## 5.2 — Balloon Callout Detector

Balloons are circles + leaders + numbers. Detect them by spatial proximity.

```python
    @staticmethod
    def detect_balloons(entities: list[ExtractedEntity]) -> list[dict]:
        """
        Detects balloon callouts by finding small circles near LEADER entities
        that contain a single numeric TEXT entity inside them.
        """
        circles = [e for e in entities if e.entity_type == "circle"]
        leaders = [e for e in entities if e.entity_type == "leader"]
        texts = [e for e in entities if e.entity_type == "text"]

        balloons = []
        for circle in circles:
            radius = circle.properties.get("radius", 0)
            # BOM balloons are typically 3–8mm radius circles
            if not (2.0 <= radius <= 10.0):
                continue

            center = circle.geometry.get("center", [0, 0, 0])
            cx, cy = center[0], center[1]

            # Find text inside the circle
            inner_text = None
            for txt in texts:
                pos = txt.geometry.get("insert", [0, 0, 0])
                dist = ((pos[0] - cx)**2 + (pos[1] - cy)**2)**0.5
                if dist <= radius:
                    val = txt.properties.get("text", "").strip()
                    if re.match(r'^\d{1,3}$', val):  # Numeric only = item no.
                        inner_text = int(val)
                        break

            if inner_text is not None:
                balloons.append({
                    "item_no": inner_text,
                    "center": [cx, cy],
                    "radius": radius
                })

        return balloons
```

---

## 5.3 — BOM ↔ Balloon Reconciliation

```python
    @staticmethod
    def reconcile(
        bom_rows: list[dict],
        balloons: list[dict],
        session_id: str
    ) -> list[AuditViolation]:
        violations = []
        bom_item_numbers = {r["item_no"] for r in bom_rows}
        balloon_item_numbers = {b["item_no"] for b in balloons}

        # Balloons pointing to non-existent BOM rows
        orphan_balloons = balloon_item_numbers - bom_item_numbers
        for orphan in orphan_balloons:
            balloon = next(b for b in balloons if b["item_no"] == orphan)
            violations.append(AuditViolation(
                audit_session_id=session_id,
                severity="critical",
                category="orphan_balloon_callout",
                description=f"Balloon callout item '{orphan}' has no matching BOM entry.",
                recommendation="Add item #{orphan} to the Bill of Materials or remove the callout.",
                standard_reference="ISO 6433 (Item References on Technical Drawings)",
                coordinates=balloon["center"]
            ))

        # BOM rows with no balloon callout in any view
        unlinked_bom = bom_item_numbers - balloon_item_numbers
        for item_no in unlinked_bom:
            violations.append(AuditViolation(
                audit_session_id=session_id,
                severity="high",
                category="unlinked_bom_item",
                description=f"BOM item '{item_no}' has no balloon callout in any drawing view.",
                recommendation="Add a balloon callout pointing to the component in the assembly view.",
                standard_reference="ISO 6433 (Item References on Technical Drawings)"
            ))

        return violations
```

---

---

# 🟠 PHASE 6: Semantic RAG Completion
### Objective: Upgrade the knowledge retrieval from keyword matching to full semantic intelligence

**Duration estimate**: 2 weeks

---

## 6.1 — Upgrade RAG Retrieval in AuditOrchestrator

Replace the MongoDB `$or` regex fallback with the fully semantic vector query as the **primary** retrieval method. The MongoDB fallback becomes secondary only.

```python
# New primary strategy in _retrieve_lessons_learned():

# STEP 1: Semantic vector query (primary)
try:
    engine = RetrievalEngine()
    # Build a rich, semantically meaningful query string
    query_parts = [drawing.file_name]
    query_parts.extend(unique_keywords[:8])
    # Add entity type hints for better semantic alignment
    dominant_entities = sorted(
        drawing.entity_counts.items(), key=lambda x: x[1], reverse=True
    )[:3]
    query_parts.extend(f"{k} drawing" for k, _ in dominant_entities)

    query_text = " ".join(query_parts)
    vector_results = engine.query(query_text, top_k=top_k, collection_name="standards_reference")

    semantic_chunks = []
    for result in vector_results:
        if result["distance"] < 0.5:  # Only highly relevant matches (< 50% cosine distance)
            meta = result.get("metadata", {})
            semantic_chunks.append(StandardChunk(
                standard_id=meta.get("standard_id", standard_ids[0]),
                section_header=meta.get("section_header", "Standard Clause"),
                content=result["text"],
                page_number=meta.get("page_number", 1)
            ))

except Exception as vec_err:
    logger.warning(f"Semantic vector retrieval failed: {vec_err}")
    semantic_chunks = []

# STEP 2: MongoDB keyword fallback (secondary supplement)
keyword_chunks = await _mongodb_keyword_query(standard_ids, unique_keywords, top_k)

# STEP 3: Merge, deduplicate, rank by relevance
all_chunks = _merge_and_rank(semantic_chunks, keyword_chunks, top_k)
return all_chunks
```

---

## 6.2 — Re-indexing Utility for Existing Standards

Add an admin endpoint to re-embed all existing MongoDB chunks into the vector store:

```python
@router.post(
    "/admin/standards/reindex",
    summary="Re-embed all standard chunks into local vector index",
    dependencies=[Depends(get_auth_token)]
)
async def reindex_standards():
    """
    Iterates all StandardChunk records in MongoDB and writes their
    embeddings to the local LanceDB JSON vector index.
    """
    all_chunks = await StandardChunk.find_all().to_list()
    provider = EmbeddingProvider()
    db_manager = LanceDBManager()

    batch_size = 50
    total_written = 0
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c.content for c in batch]
        vectors = provider.embed_texts(texts)
        records = [
            {"vector": v, "text": t, "metadata": {
                "standard_id": str(c.standard_id),
                "section_header": c.section_header,
                "chunk_index": c.chunk_index
            }}
            for v, t, c in zip(vectors, texts, batch)
        ]
        db_manager.write_embeddings("standards_reference", records)
        total_written += len(records)

    return {"reindexed": total_written}
```

---

---

# 🟡 PHASE 7: Revision Intelligence
### Objective: Support the Rev A → Rev B comparison workflow that occupies 30–90 min of engineer time

**Duration estimate**: 3 weeks

---

## 7.1 — Revision Chain Data Model

```python
# In DrawingDocument model — add revision linkage:
class DrawingDocument(Document):
    # ... existing fields ...
    part_number: str | None = None          # Extracted from title block
    revision_letter: str | None = None      # "A", "B", "C", etc.
    previous_revision_id: str | None = None # Points to the prior rev drawing
    is_latest_revision: bool = True
```

## 7.2 — Automatic Revision Detection on Upload

```python
# In ExtractionPipeline.run() — after parsing:

# Attempt to auto-detect revision info from title block
part_no = _extract_title_field(entities, ["PARTNO", "DWG NO", "図面番号"])
rev_letter = _extract_title_field(entities, ["REV", "REVISION", "改訂"])

if part_no:
    drawing.part_number = part_no
    drawing.revision_letter = rev_letter

    # Find previous revision of same part number
    previous = await DrawingDocument.find_one(
        DrawingDocument.part_number == part_no,
        DrawingDocument.is_latest_revision == True,
        DrawingDocument.id != drawing.id
    )
    if previous:
        drawing.previous_revision_id = str(previous.id)
        previous.is_latest_revision = False
        await previous.save()
        # Automatically trigger comparison audit
        await _auto_trigger_comparison(str(drawing.id), str(previous.id))

drawing.is_latest_revision = True
await drawing.save()
```

---

---

# 🟡 PHASE 8: Engineer Feedback Loop
### Objective: Make the AI smarter after every audit through structured human corrections

**Duration estimate**: 2–3 weeks

---

## 8.1 — Violation Review Endpoints

```python
# New endpoints for engineer feedback on AI violations:
@router.patch("/audits/violations/{id}/review")
async def review_violation(
    id: str,
    is_valid: bool,      # Engineer agrees/disagrees with the violation
    remarks: str = "",   # Optional correction note
    session_token: str = Depends(get_session_token)
):
    """
    Records engineer feedback on an AI-detected violation.
    Valid=True: confirmed, feeds into lessons learned.
    Valid=False: rejected hallucination, improves accuracy filter.
    """
    violation = await AuditViolation.get(id)
    violation.is_resolved = True
    violation.checker_remarks = remarks
    violation.resolution_type = "confirmed" if is_valid else "rejected_hallucination"
    await violation.save()

    # If confirmed → save to vector store as a lessons-learned record
    if is_valid:
        await _save_as_lesson(violation)
```

---

## 8.2 — Lessons Learned Auto-Accumulation

Every engineer-confirmed violation becomes a RAG lesson:

```python
async def _save_as_lesson(violation: AuditViolation):
    """
    Converts a confirmed violation into a searchable lessons-learned record
    in the vector database for future audit context injection.
    """
    lesson_text = (
        f"[CONFIRMED FINDING] Category: {violation.category}\n"
        f"Description: {violation.description}\n"
        f"Recommendation: {violation.recommendation}\n"
        f"Standard: {violation.standard_reference or 'Company Standard'}\n"
        f"Severity: {violation.severity}\n"
        f"Engineer note: {violation.checker_remarks}"
    )

    provider = EmbeddingProvider()
    db_manager = LanceDBManager()

    vector = provider.embed_texts([lesson_text])[0]
    db_manager.write_embeddings("lessons_learned", [{
        "vector": vector,
        "text": lesson_text,
        "metadata": {
            "category": violation.category,
            "severity": violation.severity,
            "standard": violation.standard_reference,
            "source": "engineer_feedback",
            "confirmed_at": datetime.now(UTC).isoformat()
        }
    }])
```

---

---

# 🟡 PHASE 9: Advanced Reporting
### Objective: Generate audit reports that look as professional as consultant deliverables

**Duration estimate**: 3 weeks

---

## 9.1 — Visual Annotation Overlay in PDF Reports

Embed a drawing PNG with violation markers directly in the PDF report:

```python
# In pdf_exporter.py:
def _embed_annotated_drawing(pdf, drawing_png: bytes, violations: list):
    """
    Overlays colored violation markers on the drawing PNG and embeds it in PDF.
    - RED circle/box = critical/high severity
    - YELLOW circle/box = medium severity
    - BLUE = low severity
    """
    from PIL import Image, ImageDraw
    import io

    img = Image.open(io.BytesIO(drawing_png)).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    SEVERITY_COLORS = {
        "critical": (220, 38, 38, 180),
        "high": (249, 115, 22, 160),
        "medium": (234, 179, 8, 140),
        "low": (96, 165, 250, 120)
    }

    for v in violations:
        coords = v.coordinates
        if not coords:
            continue
        color = SEVERITY_COLORS.get(v.severity, (128, 128, 128, 120))
        x, y = coords[0], coords[1]
        # Draw marker box at violation coordinate
        draw.rectangle([x-15, y-15, x+15, y+15], outline=color, width=3)

    # Embed annotated image in PDF
    annotated_bytes = io.BytesIO()
    img.save(annotated_bytes, format="PNG")
    pdf.image(annotated_bytes, w=180)
```

---

## 9.2 — Compliance Trend Dashboard Endpoint

```python
@router.get("/analytics/compliance-trend")
async def compliance_trend(
    drawing_part_number: str | None = None,
    client_name: str | None = None,
    days: int = 90
):
    """Returns compliance score trend over time for dashboard visualization."""
    # Query audit sessions grouped by drawing/date
    # Returns time-series data for the frontend chart
```

---

---

# 🟢 PHASE 10: Enterprise Hardening
### Objective: Production-grade reliability, performance, and scalability

**Duration estimate**: 4–6 weeks

---

## 10.1 — Batch Audit Pipeline

Allow multiple drawings to be queued and audited in parallel:

```python
@router.post("/audits/batch")
async def launch_batch_audit(
    drawing_ids: list[str],
    standard_id: str,
    client_name: str | None = None
):
    """Enqueues multiple drawings for sequential/parallel compliance auditing."""
```

---

## 10.2 — Drawing Similarity Engine

Detect when engineers accidentally submit near-duplicate or clone drawings:

```python
class DrawingSimilarityEngine:
    """
    Detects clone drawings by comparing geometry fingerprints
    using entity count distributions and spatial arrangement.
    """
    @staticmethod
    def compute_fingerprint(drawing: DrawingDocument) -> list[float]:
        # Encode entity type distribution as a normalized vector
        counts = drawing.entity_counts
        total = sum(counts.values()) or 1
        return [counts.get(k, 0) / total for k in
                ["line", "circle", "arc", "text", "dimension", "block"]]
```

---

## 10.3 — Multi-Sheet Drawing Support

Many complex drawings span 4–12 sheets (Sheet 1/4, 2/4, etc.). Current system only processes the first model space layout.

Add full paper space layout enumeration to `DXFParser` and a sheet selection UI in the frontend.

---

## 10.4 — Custom Rule Builder (Admin UI)

Allow admins to define company-specific rules without code:

```typescript
// Frontend: Admin → Rule Builder
interface CustomRule {
  name: string;
  trigger: "entity_type" | "layer_name" | "text_contains" | "dimension_range";
  condition: string;           // e.g. "text_contains: 'ISO 2768'"
  severity: "critical" | "high" | "medium" | "low";
  description_template: string;
  recommendation: string;
  standard_reference: string;
}
```

---

## 10.5 — Digital Signature Integration

For fully compliant QMS (Quality Management System) integration, allow engineers to digitally sign their review completion:

```python
# AuditSession — add signature fields
class AuditSession(Document):
    # ... existing fields ...
    review_signed_by: str | None = None
    review_signed_at: datetime | None = None
    review_signature_hash: str | None = None  # SHA-256 of session+reviewer+timestamp
```

---

---

## 📋 Complete Implementation Sequence

```
Phase 1  ████████████░░░░░░░░░░░░░░░░░░   Foundation Repair        [2 weeks]
Phase 2  ░░░░░░░░████████████░░░░░░░░░░░   Rule Engine Expansion   [3 weeks]
Phase 3  ░░░░░░░░░░░░████████████░░░░░░░   Visual AI Grounding     [3 weeks]
Phase 4  ░░░░░░░░░░░░░░░░░████████░░░░░░   Entity Extraction       [2 weeks]
Phase 5  ░░░░░░░░░░░░░░░░░░░░████████░░░   BOM & Balloon           [3 weeks]
Phase 6  ░░░░░░░░░░░░░░░░░░░░░░░░████░░░   Semantic RAG            [2 weeks]
Phase 7  ░░░░░░░░░░░░░░░░░░░░░░░░░░████░   Revision Intelligence   [3 weeks]
Phase 8  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░██   Feedback Loop           [3 weeks]
Phase 9  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░█   Advanced Reporting      [3 weeks]
Phase 10 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   Enterprise Hardening    [6 weeks]

                                           Total: ~30 weeks (~7 months)
```

---

## 🎯 Expected Coverage After All Phases

| Checking Area | Before | After Phase 3 | Final (Phase 10) |
|---|---|---|---|
| Title Block Validation | 20% | 50% | 95% |
| Layer/View Integrity | 30% | 70% | 90% |
| Dimension Completeness | 15% | 80% | 90% |
| GD&T Validation | 0% | 70% | 85% |
| BOM Reconciliation | 0% | 80% | 95% |
| Visual Layout Check | 0% | 85% | 90% |
| Revision Comparison | 30% | 30% | 95% |
| Notes Completeness | 25% | 60% | 85% |
| Surface/Weld Symbols | 0% | 40% | 80% |
| **Overall Alignment** | **~35%** | **~70%** | **~90%** |
