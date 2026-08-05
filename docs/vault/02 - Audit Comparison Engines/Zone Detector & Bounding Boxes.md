---
title: Zone Detector & Bounding Boxes
type: engine
tags: [engine, zone-detector, bounding-box, taxonomy]
---

# 🔲 Zone Detector & Bounding Boxes

The **Zone Detector** (`zone_detector.py`) is a content-aware zone segmentation system that identifies where key engineering zones physically reside in CAD world coordinates $(x, y)$.

---

## 📐 The 7 Canonical Drawing Zones

```mermaid
graph TD
    subgraph Sheet["Drawing Sheet Boundaries"]
        TL["title_upper_left (Teal #2dd4bf)"] --- Views["views (Sky Blue #38bdf8)"]
        Views --- BOM["bom (Emerald #34d399)"]
        Views --- ISO["iso (Violet #c084fc)"]
        Notes["notes (Rose #fb7185)"] --- Views
        Tol["tolerance (Amber #fbbf24)"] --- Title["title (Indigo #818cf8)"]
    end
```

`ZONE_ANCHORS` holds the *candidate* phrases. Which ones actually fire on a given drawing is a
different question, and is now recorded per drawing under `zones["_anchor_matches"]`. The right
column below is the **measured** answer on the 4-drawing corpus (2026-07-29) — use it, not the
candidate list, when deciding which anchor to tune.

| Zone Key | Description | Anchors that ACTUALLY fire (4/4 drawings unless noted) | Render Color |
| :--- | :--- | :--- | :--- |
| **`title`** | Bottom-Right Title Block | `approved`, `checked`, `designed`, `drawn`, `図面番号`, `設計`, plus `訂正` on 2 of 4 | Indigo `#818cf8` |
| **`title_upper_left`** | Top-Left Metadata Block | `part no`, `stock q'ty`, `t. q'ty`, `unit no`, `コードno`, `ユニットno`, `在庫棚入庫`, `総製作個数` | Teal `#2dd4bf` |
| **`bom`** | Bill of Materials / Parts Table | `finished weight`, `material weight`, `仕上重量`, `素材重量` | Emerald `#34d399` |
| **`tolerance`** | General Tolerance Legend Block | `tolerances unless otherwise specified`, `roughness range`, `表面粗さ` | Amber `#fbbf24` |
| **`notes`** | Technical Notes & Reqs | `なきこと`, `仕上げ`, `面取り` | Rose `#fb7185` |
| **`iso`** | 3D Isometric View | **none — resolved geometrically**, by ellipse density | Violet `#c084fc` |
| **`views`** | Main Geometry Drawing Views | **none — it is the sheet**; exclusion lives in `in_views()` | Sky Blue `#38bdf8` |

> [!WARNING] The documented anchors were not the operative ones
> This table previously listed `tolerance` as anchored by `指示外公差 / 指示無き公差 / 表示外公差 /
> 仕上精度`. **None of those fire on any corpus drawing** — the phrases that actually resolve the
> zone are the three above. Likewise `bom` was listed as `parts list / bill of materials / 部品表 /
> 材料明細`, none of which match either. Someone tuning from the old table would have been editing
> dead anchors. Check `_anchor_matches` before touching `ZONE_ANCHORS`.

---

## 🔍 Visual Bounding Box Endpoint (`GET /drawings/{id}/zones`)

To allow engineers and developers to debug zone detection professionally:
1. **Endpoint**: `GET /api/v1/drawings/{id}/zones` returns the exact CAD world coordinates `(xmin, ymin, xmax, ymax)` and resolution confidence. **Three** confidence values, not two:
   - `content_aware` — semantic anchor found and flood-filled. A measurement.
   - `percentage_fallback` — no anchor; percentage grid over real sheet bounds. A plausible guess, rendered dashed with a `?`.
   - `percentage_fallback_no_sheet_bounds` — `compute_drawing_bounds` returned nothing, so **all seven zones are the literal `(0, 0, 1000, 1000)` placeholder**. This one must never be drawn: seven identical rectangles near the origin read as a broken overlay rather than as failed bounds detection.
2. **Canvas Rendering**: Rendered inside `CanvasRenderer` with color-coded borders, semi-transparent fill, and top-left badge pills.
3. **Toggle Control**: **`Edit Zone Boxes`** in the ⋮ View menu of the 2D Review Workspace. The former read-only `Zones` toolbar button was removed — it drew a near-identical box set to the editor with different semantics, and there was no way to tell which one a drag would affect.

---

---

## 📏 Current accuracy (re-measured 2026-07-29)

The warning that used to sit here — `iso` never detected, `notes`/`views`/`tolerance` moving
33–64pp — described the state before the ingestion and detector fixes. Superseded:

| Zone | Spread | Detected |
| :--- | ---: | :--- |
| bom | 1.7pp | 4/4 |
| iso | 1.8pp | 2/4 — the two drawings that *have* an isometric view |
| views | 0.0pp | 4/4 — it is the sheet, so it cannot vary |
| notes | 11.3pp | 4/4 |
| tolerance | 11.3pp | 4/4 |
| title | 11.6pp | 4/4 |
| title_upper_left | 25.8pp | 4/4 |

> [!IMPORTANT] Two things not to misread
> - **`views` at 0.0pp is not stability.** The box is the sheet by definition. `views` is a
>   *predicate*: use `zone_detector.in_views(x, y, regions)`, which is
>   `inside(sheet) AND NOT inside(any other zone)`. The raw box admits every title block, BOM row
>   and notes line on the sheet. Any consumer using it as a containment region must subtract the
>   siblings via `views_exclusions()`.
> - **`iso` at 2/4 is correct, not a failure.** Roughly half of real sheets have no isometric view.
>   Returning nothing for those is the intended behaviour.
>
> The corpus is 4 drawings that are effectively **2 layouts × 2 near-copies**, n≈2. Read
> [[Gotcha - Zone Detection Accuracy & Stability]] before trusting a number here or tuning an anchor.

## 🔗 Related Notes
- See [[Gotcha - Zone Detection Accuracy & Stability]]
- Return to [[00 - Map of Content (MOC)]]
- See [[RAG Engine (Deterministic)]]
- See [[CanvasRenderer & Entity Drawing]]
