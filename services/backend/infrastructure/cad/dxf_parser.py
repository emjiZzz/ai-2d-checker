import time
from collections import Counter
from pathlib import Path
from typing import Any

import ezdxf

from ...core.security import validate_sandboxed_path
from ...logger import logger
from .entity_mapper import GEOMETRY_SCHEMA, SCALED_PROPERTY_KEYS, EntityMapper
from .viewport_transform import NO_VIEWPORT, TRANSFORM_VERSION, ViewportTransform

# Property keys holding coordinate pairs that must be projected alongside geometry.
# `bbox` is [[xmin, ymin], [xmax, ymax]].
PROJECTED_PROPERTY_POINT_LISTS: tuple[str, ...] = ("bbox",)

# Below this, a Z value is treated as "on the drawing plane" rather than as 3D content.
# Deliberately loose: CAD exporters round-trip coordinates through decimal text, so a
# nominally flat drawing can carry Z values a few ULPs off zero.
Z_EPSILON = 1e-9

# DXF entity types that carry genuine 3D geometry and are NOT handled by
# `EntityMapper.map_any`, so they are dropped at ingestion. Counted (never mapped) purely
# so a drawing that looks empty in a 3D view can explain why -- see `summarize_three_d`.
UNMAPPED_3D_TYPES: frozenset[str] = frozenset({
    "3DFACE", "MESH", "3DSOLID", "BODY", "REGION",
    "SURFACE", "EXTRUDEDSURFACE", "REVOLVEDSURFACE", "LOFTEDSURFACE",
    "SWEPTSURFACE", "PLANESURFACE", "NURBSURFACE",
})


def summarize_three_d(
    entities: list[dict[str, Any]], unmapped_counts: dict[str, int]
) -> dict[str, Any]:
    """Report how much genuine 3D geometry a drawing carries.

    Two independent signals, because they fail independently:

    * `nonzero_z` counts non-zero Z on entities that *were* mapped. This is what a 3D
      view can actually draw today, so it drives `renderable`.
    * `unmapped_types` counts entity types dropped by `map_any` (see `UNMAPPED_3D_TYPES`).
      Those contribute nothing renderable, so a drawing can be full of solids and still
      report `nonzero_z == 0`.

    Keeping them apart is the whole point: it separates "this drawing is flat" from "this
    drawing's 3D content did not survive ingestion". Collapsed into one boolean those are
    indistinguishable to every caller, which is precisely how the dropped ELLIPSE/SPLINE
    geometry stayed hidden for so long.

    Walks `GEOMETRY_SCHEMA`'s coordinate keys rather than every geometry value, so an
    ellipse's `major_axis` is correctly excluded -- it is a direction vector whose third
    component is not an elevation.
    """
    nonzero = 0
    z_min: float | None = None
    z_max: float | None = None
    types_with_z: Counter = Counter()

    def note(point: Any, entity_type: str) -> None:
        nonlocal nonzero, z_min, z_max
        if not isinstance(point, (list, tuple)) or len(point) < 3:
            return
        try:
            z = float(point[2])
        except (TypeError, ValueError):
            return
        z_min = z if z_min is None else min(z_min, z)
        z_max = z if z_max is None else max(z_max, z)
        if abs(z) > Z_EPSILON:
            nonzero += 1
            types_with_z[entity_type] += 1

    for entity in entities:
        entity_type = entity.get("entity_type", "")
        schema = GEOMETRY_SCHEMA.get(entity_type)
        if not schema:
            continue
        geometry = entity.get("geometry") or {}

        for key in schema.get("points", ()):
            note(geometry.get(key), entity_type)

        for key in schema.get("point_lists", ()):
            for point in geometry.get(key) or ():
                note(point, entity_type)

        for key in schema.get("point_list_groups", ()):
            for group in geometry.get(key) or ():
                for point in group or ():
                    note(point, entity_type)

    return {
        # There is 3D content in the file, whether or not we can draw it.
        "has_3d": bool(nonzero) or bool(unmapped_counts),
        # We can draw it. The 3D view gates on this; `has_3d and not renderable` is the
        # case that needs an explanation in the UI rather than an empty viewport.
        "renderable": bool(nonzero),
        "nonzero_z": nonzero,
        "z_range": [z_min, z_max] if z_min is not None else None,
        "entity_types": dict(types_with_z),
        "unmapped_types": dict(unmapped_counts),
    }


def project_mapped_entity(
    mapped: dict[str, Any], transform: ViewportTransform
) -> tuple[int, float]:
    """Project every coordinate of a mapped entity from model space into paper space.

    Schema-driven via `GEOMETRY_SCHEMA` so all entity types are covered uniformly.
    The previous inline implementation hand-wrote a branch per type and silently
    omitted hatch, tolerance, leader, multileader and block, leaving those five in
    model space while everything else moved to paper space -- invisible behind the
    raster PNG, but scattered geometry the moment anything renders vectors.

    The whole entity is pinned to the viewport chosen by its first coordinate rather
    than resolving each point independently. An entity belongs to one view, so
    per-point resolution could tear geometry that straddles a viewport edge; pinning
    also makes the inverse exact, since the index is recorded on the entity.

    Returns (viewport_index, scale) so the caller can persist them for `unproject`.
    """
    if transform.is_identity:
        return NO_VIEWPORT, 1.0

    schema = GEOMETRY_SCHEMA.get(mapped.get("entity_type", ""))
    if not schema:
        return NO_VIEWPORT, 1.0

    geometry = mapped.get("geometry") or {}
    properties = mapped.get("properties") or {}

    state: dict[str, Any] = {"index": None, "scale": 1.0, "resolved": False}

    def project_point(point: Any) -> list[float]:
        result = transform.project(float(point[0]), float(point[1]), state["index"])
        if not state["resolved"]:
            state["index"] = result.viewport_index
            state["scale"] = result.scale
            state["resolved"] = True
        # Z passes through unchanged, and is deliberately NOT transformed: a paper-space
        # viewport is a window onto the model's XY plane, so it has no Z axis to map into
        # and no scale that means anything for one. The third component stays the
        # model-space elevation it already was.
        #
        # It used to be dropped here, which destroyed the only 3D information a DXF
        # carries -- on every drawing with a paper-space layout, i.e. 6 of the 11 files in
        # the local corpus. Arity is preserved rather than normalised to 3: `bbox` and the
        # hatch/ellipse/spline tessellations are genuinely 2D and must stay 2-component.
        # See docs/vault/06 - .../Gotcha - Z Is Truncated by the Paper-Space Projection.
        if len(point) > 2:
            try:
                return [result.x, result.y, float(point[2])]
            except (TypeError, ValueError):
                pass
        return [result.x, result.y]

    def is_point(value: Any) -> bool:
        return isinstance(value, (list, tuple)) and len(value) >= 2 and not isinstance(value[0], (list, tuple))

    for key in schema.get("points", ()):
        value = geometry.get(key)
        if is_point(value):
            geometry[key] = project_point(value)

    for key in schema.get("point_lists", ()):
        value = geometry.get(key)
        if isinstance(value, list) and value:
            geometry[key] = [project_point(p) if is_point(p) else p for p in value]

    for key in schema.get("point_list_groups", ()):
        value = geometry.get(key)
        if isinstance(value, list) and value:
            geometry[key] = [
                [project_point(p) if is_point(p) else p for p in group] if isinstance(group, list) else group
                for group in value
            ]

    for key in PROJECTED_PROPERTY_POINT_LISTS:
        value = properties.get(key)
        if isinstance(value, list) and value and all(is_point(p) for p in value):
            properties[key] = [project_point(p) for p in value]

    # Scale distances only once the viewport is known. If no coordinate resolved a
    # viewport (an entity with no geometry), leave sizes untouched.
    if state["resolved"]:
        scale = state["scale"]
        for key in schema.get("lengths", ()):
            if isinstance(geometry.get(key), (int, float)):
                geometry[key] = geometry[key] * scale

        # Vectors are offsets from the entity's own origin, so they take the scale but
        # not the translation. Running an ellipse's major axis through project_point
        # would re-anchor it to the viewport and reshape the ellipse.
        for key in schema.get("vectors", ()):
            value = geometry.get(key)
            if is_point(value):
                geometry[key] = [float(v) * scale for v in value]
        for key in SCALED_PROPERTY_KEYS:
            if isinstance(properties.get(key), (int, float)):
                properties[key] = properties[key] * scale

    return (state["index"] if state["resolved"] else NO_VIEWPORT), state["scale"]


class DXFParser:
    """
    Parses a DXF file using ezdxf, extracting layers, geometry, dimensions, blocks,
    and metadata inside a secure path sandbox.
    """
    def parse_file(self, file_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], dict[str, Any]]:
        """
        Parses a canonical sandboxed DXF file.
        Returns:
            entities: List of mapped geometries.
            layers: List of active layer properties.
            counts: Dictionary of entity totals.
            metadata: Structured header metadata.
        """
        # 1. Enforce sandbox path traversal bounds
        validate_sandboxed_path(file_path)

        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"DXF target file not found for parsing: {file_path}")

        logger.info(f"Initiating ezdxf parsing for file: {file_path}")
        start_time = time.time()

        try:
            # 1. Open DXF using byte-preserving latin-1 to perfectly preserve Shift-JIS/CP932 raw bytes
            doc = ezdxf.readfile(str(file_path), encoding="latin-1")
            logger.info(f"DXF loaded with byte-preserving latin-1. Header codepage: {doc.header.get('$DWGCODEPAGE')}")
        except Exception as read_err:
            logger.warning(f"Latin-1 read failed, attempting standard auto-detect: {str(read_err)}")
            try:
                # 2. Let ezdxf auto-detect based on DXF header ($DWGCODEPAGE)
                doc = ezdxf.readfile(str(file_path))
                logger.info(f"DXF auto-detected encoding: {doc.encoding}")
            except (ezdxf.DXFError, UnicodeDecodeError):
                try:
                    # 3. Force CP932 (Shift-JIS) for Japanese files that lack header codepages
                    logger.info(f"Auto-detect failed. Trying CP932 (Shift-JIS) for: {file_path}")
                    doc = ezdxf.readfile(str(file_path), encoding="cp932")
                except (ezdxf.DXFError, UnicodeDecodeError):
                    try:
                        # 4. Force UTF-8
                        doc = ezdxf.readfile(str(file_path), encoding="utf-8")
                    except ezdxf.DXFError as dxf_err:
                        logger.error(f"Failed to decode DXF structure: {str(dxf_err)}")
                        raise ValueError(f"Corrupt or incompatible DXF structure: {str(dxf_err)}")
                    except Exception as e:
                        logger.error(f"Failed to read file: {str(e)}")
                        raise

        # 2. Extract Layers
        # lineweight/linetype are recorded here as well as on entities: an entity
        # carrying BYLAYER (-1) resolves its real stroke against these values.
        layers = []
        for layer in doc.layers:
            layers.append({
                "entity_type": "layer",
                "layer": layer.dxf.name,
                "properties": {
                    "color": layer.dxf.color,
                    "is_locked": layer.is_locked(),
                    "is_frozen": layer.is_frozen(),
                    "is_off": not layer.is_on(),
                    "lineweight": getattr(layer.dxf, "lineweight", -1),
                    "linetype": getattr(layer.dxf, "linetype", "Continuous"),
                },
                "geometry": {}
            })

        # 3. Extract Graphical Geometries from Model Space and Paper Space (Layouts)
        entities = []
        counts = {
            "line": 0,
            "circle": 0,
            "arc": 0,
            # Always reported, including as 0, so "this drawing has no ellipses" is
            # distinguishable from "ellipses were never counted" -- the ambiguity that
            # hid them being dropped at ingestion in the first place.
            "ellipse": 0,
            "spline": 0,
            "polyline": 0,
            "dimension": 0,
            "text": 0,
            "block": 0,
            "layer": len(layers)
        }

        # Identify the active paperspace layout and build the invertible model<->paper
        # projection. Identity when the drawing has no paper-space viewports.
        transform = ViewportTransform.from_document(doc)

        # 3D entity types `map_any` cannot handle. Tallied as they go past so their
        # absence downstream is reported rather than silent -- see `summarize_three_d`.
        unmapped_3d: Counter = Counter()

        def process_entity(entity, layout_name, depth=0, is_dimension=False, parent_handle=None):
            if depth > 10:
                logger.warning(f"Recursive block/dimension explosion depth limit reached at entity: {entity.dxftype()}")
                return

            dxftype = entity.dxftype()

            if dxftype in UNMAPPED_3D_TYPES:
                unmapped_3d[dxftype] += 1

            if dxftype == "INSERT":
                # Explode the block so its content is individually addressable, and
                # tag each child with the owning INSERT's handle. The INSERT itself is
                # still recorded below as a container: `virtual_entities()` does not
                # yield attached ATTRIBs, so it is the only carrier of title-block
                # attribute values.
                insert_handle = getattr(entity.dxf, "handle", None)
                try:
                    for sub_ent in entity.virtual_entities():
                        process_entity(sub_ent, layout_name, depth + 1, is_dimension, insert_handle)
                except Exception as ex:
                    logger.debug(f"Could not explode block {getattr(entity.dxf, 'name', 'unknown')}: {ex}")

            mapped = EntityMapper.map_any(entity)
            if mapped:
                props = mapped["properties"]
                props["layout_space"] = layout_name
                if parent_handle:
                    props["parent_handle"] = parent_handle

                # Project model-space geometry (and dimensions rendered through a
                # paper-space viewport) into paper coordinates. Paper-space entities
                # are already in the target space and are left alone.
                needs_projection = (layout_name.lower() == "model") or is_dimension
                if needs_projection and not transform.is_identity:
                    viewport_index, scale = project_mapped_entity(mapped, transform)
                    props["space"] = "paper"
                    props["viewport_index"] = viewport_index
                    props["viewport_scale"] = scale
                else:
                    props["space"] = "paper" if not transform.is_identity else "model"
                    props["viewport_index"] = NO_VIEWPORT
                    props["viewport_scale"] = 1.0

                entities.append(mapped)
                entity_type = mapped["entity_type"]
                if entity_type in counts:
                    counts[entity_type] += 1
                else:
                    counts[entity_type] = 1

        for layout in doc.layouts:
            layout_entities = list(layout)
            for entity in layout_entities:
                process_entity(entity, layout.name)

        # Extract XREFs from block definitions (XREF detection - Phase 4.4)
        for block in doc.blocks:
            if hasattr(block, "is_xref") and block.is_xref:
                entities.append({
                    "entity_type": "xref",
                    "layer": "0",
                    "properties": {
                        "handle": block.block_record.dxf.handle if hasattr(block.block_record, "dxf") else "XREF",
                        "name": block.name,
                        "xref_path": block.xref_path if hasattr(block, "xref_path") else "",
                        "is_unresolved": block.is_xref_unresolved if hasattr(block, "is_xref_unresolved") else False
                    },
                    "geometry": {}
                })
                counts["xref"] = counts.get("xref", 0) + 1

        # 4. Extract standard metadata headers
        metadata = {
            "ezdxf_version": ezdxf.__version__,
            "acad_version": doc.acad_release,
            "handseed": doc.header.get("$HANDSEED", "unknown"),
            "measurement": doc.header.get("$MEASUREMENT", -1), # 0 = Inch, 1 = Metric
            "extmin": list(doc.header.get("$EXTMIN", [0, 0, 0])),
            "extmax": list(doc.header.get("$EXTMAX", [0, 0, 0])),
            # The model<->paper projection applied to the geometry above. Persisted
            # so a stored coordinate can be mapped back into the source file's model
            # space -- the prerequisite for writing redlines into CAD.
            "viewport_transform": transform.to_dict(),
            "transform_version": TRANSFORM_VERSION,
            "coordinate_space": "model" if transform.is_identity else "paper",
            # How much genuine 3D geometry survived ingestion, and how much did not.
            # Consumed by the desktop 3D view to decide whether it has anything to draw.
            "three_d": summarize_three_d(entities, dict(unmapped_3d)),
        }

        three_d = metadata["three_d"]
        if three_d["unmapped_types"]:
            logger.warning(
                f"Dropped {sum(three_d['unmapped_types'].values())} 3D entities that "
                f"`EntityMapper.map_any` does not handle: {three_d['unmapped_types']}. "
                "They will not appear in any view."
            )
        elif three_d["renderable"]:
            logger.info(
                f"3D geometry present: {three_d['nonzero_z']} non-zero Z coordinates "
                f"over {three_d['z_range']} in {three_d['entity_types']}."
            )

        # Dynamic Layout Analysis
        lines = []
        for e in entities:
            if e.get("entity_type") == "line" and "geometry" in e:
                geo = e["geometry"]
                if "start" in geo and "end" in geo:
                    lines.append((geo["start"], geo["end"]))
            elif e.get("entity_type") == "polyline" and "geometry" in e:
                geo = e["geometry"]
                if "vertices" in geo:
                    pts = geo["vertices"]
                    for i in range(len(pts) - 1):
                        lines.append((pts[i], pts[i+1]))
                elif "points" in geo:
                    pts = geo["points"]
                    for i in range(len(pts) - 1):
                        lines.append((pts[i], pts[i+1]))

        default_regions = {
            "views":         { "xMin": 0.04, "xMax": 0.68, "yMin": 0.12, "yMax": 0.88 },
            "notes":         { "xMin": 0.04, "xMax": 0.38, "yMin": 0.18, "yMax": 0.62 },
            "bom":           { "xMin": 0.62, "xMax": 0.98, "yMin": 0.04, "yMax": 0.44 },
            "title":         { "xMin": 0.38, "xMax": 0.98, "yMin": 0.72, "yMax": 0.98 },
            "titleUpperLeft":{ "xMin": 0.02, "xMax": 0.35, "yMin": 0.02, "yMax": 0.35 },
            "iso":           { "xMin": 0.62, "xMax": 0.98, "yMin": 0.42, "yMax": 0.74 }
        }
        
        metadata["regions"] = default_regions

        if lines:
            try:
                min_x = min(min(p1[0], p2[0]) for p1, p2 in lines)
                max_x = max(max(p1[0], p2[0]) for p1, p2 in lines)
                min_y = min(min(p1[1], p2[1]) for p1, p2 in lines)
                max_y = max(max(p1[1], p2[1]) for p1, p2 in lines)
                
                width = max_x - min_x
                height = max_y - min_y
                if width > 0 and height > 0:
                    tr_lines = [l for l in lines if (l[0][0]-min_x)/width > 0.6 and (l[0][1]-min_y)/height < 0.5]
                    br_lines = [l for l in lines if (l[0][0]-min_x)/width > 0.4 and (l[0][1]-min_y)/height > 0.6]
                    
                    def get_bounds(quad_lines, default_box):
                        if not quad_lines: return default_box
                        qx_min = min(min(p1[0], p2[0]) for p1, p2 in quad_lines)
                        qx_max = max(max(p1[0], p2[0]) for p1, p2 in quad_lines)
                        qy_min = min(min(p1[1], p2[1]) for p1, p2 in quad_lines)
                        qy_max = max(max(p1[1], p2[1]) for p1, p2 in quad_lines)
                        return {
                            "xMin": max(0.0, (qx_min - min_x) / width - 0.01),
                            "xMax": min(1.0, (qx_max - min_x) / width + 0.01),
                            "yMin": max(0.0, (qy_min - min_y) / height - 0.01),
                            "yMax": min(1.0, (qy_max - min_y) / height + 0.01)
                        }
                    
                    metadata["regions"]["bom"] = get_bounds(tr_lines, default_regions["bom"])
                    metadata["regions"]["title"] = get_bounds(br_lines, default_regions["title"])
            except Exception:
                pass

        # Content-aware zone detection — run at ingestion time so results are
        # persisted into drawing.metadata and available to both the AI engine
        # and the React frontend without re-computing them on every comparison.
        try:
            from ..audit.bom.zone_detector import detect_zones_by_content
            # Build lightweight entity list from raw dicts (zone_detector accepts both models and dicts)
            class _DictEntity:
                """Thin wrapper so zone_detector can call getattr(e, ...) on raw dicts."""
                def __init__(self, d):
                    self.entity_type = d.get("entity_type", "")
                    self.layer = d.get("layer", "")
                    self.geometry = d.get("geometry", {}) or {}
                    self.properties = d.get("properties", {}) or {}
            dict_entities = [_DictEntity(e) for e in entities]
            detected = detect_zones_by_content(dict_entities)
            # Store safe zones as a list of absolute-coordinate bounding boxes
            # Format: [[xmin, ymin, xmax, ymax], ...]  -- JSON-serializable
            safe_bbox_list = []
            if detected.get("tolerance"):
                safe_bbox_list.append(list(detected["tolerance"]))
            # Also include any explicitly detected safe_zones from the detector
            for sz in (detected.get("safe_zones") or []):
                if sz and sz not in safe_bbox_list:
                    safe_bbox_list.append(list(sz))
            metadata["safe_zones"] = safe_bbox_list
            logger.info(f"Content-aware zone detection complete. Detected safe zones: {len(safe_bbox_list)}")
        except Exception as zone_err:
            logger.warning(f"Content-aware zone detection failed during ingestion (non-fatal): {zone_err}")
            metadata["safe_zones"] = []


        # Transcode all string elements in layers and entities to their correct drawing encoding
        doc_encoding = getattr(doc, "encoding", "cp932") or "cp932"
        # Normalize to lower standard
        if doc_encoding.lower() in ("ansi_932", "cp932", "ms932", "shift_jis", "sjis"):
            doc_encoding = "cp932"
        
        logger.info(f"Performing deep CJK transcoding using drawing encoding: {doc_encoding}")
        
        def transcode_value(val: Any) -> Any:
            if isinstance(val, str):
                try:
                    b = val.encode('latin1')
                except Exception:
                    return val
                for enc in (doc_encoding, 'cp932', 'utf-8', 'latin-1'):
                    if not enc:
                        continue
                    try:
                        return b.decode(enc)
                    except Exception:
                        continue
                return b.decode('utf-8', errors='replace')
            elif isinstance(val, dict):
                return {transcode_value(k): transcode_value(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [transcode_value(v) for v in val]
            return val

        entities = transcode_value(entities)
        layers = transcode_value(layers)

        duration = time.time() - start_time
        logger.info(
            f"Successfully parsed DXF in {duration:.4f}s. "
            f"Extracted {len(entities)} elements across {len(layers)} layers."
        )

        return entities, layers, counts, metadata
