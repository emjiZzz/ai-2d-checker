---
title: ezdxf Entity Extraction
type: cad
tags: [cad, ezdxf, python, parsing, mtext]
---

# 📐 ezdxf Entity Extraction

The `ezdxf` parsing infrastructure (`DXFParser` in `services/backend/infrastructure/cad/dxf_parser.py`) is the core vector parsing library used to extract entities from `.dxf` files.

---

## 🛠️ Supported CAD Entity Types

The authoritative list is the dispatch in `EntityMapper.map_any` — anything not branched there
returns `None` and is **silently discarded**, which is how ellipses and splines went missing for
so long (see below).

- **`TEXT` / `MTEXT`**: Single-line and multi-line text annotations.
- **`ATTRIB` / `ATTDEF`**: Block attributes (Title Block data, BOM rows).
- **`DIMENSION`**: Linear, aligned, angular, radial, and diameter dimensions.
- **`LEADER` / `MULTILEADER`**: Callout lines pointing to features.
- **`LINE` / `CIRCLE` / `ARC`**: Vector geometry.
- **`POLYLINE` / `LWPOLYLINE`**: Polyline geometry.
- **`ELLIPSE`** *(added 2026-07-29)*: Kept as its own type, not flattened, because an ellipse is a
  circle seen at an angle — its presence is what identifies an isometric view.
- **`SPLINE`** *(added 2026-07-29)*: Flattened via `flattening()`, with control points as fallback.
- **`HATCH`**: Fill boundaries as closed island loops.
- **`TOLERANCE`**: GD&T frames — deliberately *not* run through the MTEXT cleaner, since `\F` font
  codes carry symbol meaning here.
- **`INSERT`**: Recorded as a container and recursively exploded; children carry `parent_handle`.

> [!WARNING]
> `map_any` fails **open** — an unhandled type is indistinguishable from a deliberately skipped
> one. Before this was fixed, 111 ellipses and 46 splines were dropped corpus-wide, taking 90% of
> one isometric view's entities with them. See [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]].

---

## 🔤 Japanese CJK Encoding & MTEXT Cleaning

1. **CP932 / Shift-JIS Support**: The file is read byte-preserving (`encoding="latin-1"`) so
   `dxf_parser.transcode_value` can recover real Shift-JIS text afterwards. Everything running
   *before* that pass — including `strip_mtext` — therefore sees raw CP932 bytes, one per character.
2. **`strip_mtext(text)`**:
   - Converts AutoCAD escape codes: `%%c` $\rightarrow$ **`Ø`**, `%%d` $\rightarrow$ **`°`**, `%%p` $\rightarrow$ **`±`**.
   - Strips paragraph breaks (`\P`) and MTEXT formatting codes (`\W...;`, `{...}`).

> [!IMPORTANT] The markup characters collide with Shift-JIS trail bytes
> A CP932 trail byte may legally be `0x5C`, `0x7B`, `0x7D` or `0x7E` — backslash and braces,
> exactly the MTEXT markup characters. Stripping markup on the byte string mutilated any character
> whose second byte was one of them: 施 (`0x8E 0x7B`) became `詩H`, ソ (`0x83 0x5C`) became `ャi`,
> and 表 (`0x95 0x5C`) — a tolerance anchor — became unmatchable.
> `_mask_sjis_markup_collisions` now protects those characters. **Read
> [[Gotcha - AutoCAD Control Escape Codes]] before touching this function.**

---

## 🔗 Related Notes
- Return to [[00 - Map of Content (MOC)]]
- See [[RAG Engine (Deterministic)]]
- See [[CanvasRenderer & Entity Drawing]]
