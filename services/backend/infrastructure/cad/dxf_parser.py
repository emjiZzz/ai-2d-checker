import time
from pathlib import Path
from typing import Any

import ezdxf

from ...core.security import validate_sandboxed_path
from ...logger import logger
from .entity_mapper import EntityMapper


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
        layers = []
        for layer in doc.layers:
            layers.append({
                "entity_type": "layer",
                "layer": layer.dxf.name,
                "properties": {
                    "color": layer.dxf.color,
                    "is_locked": layer.is_locked(),
                    "is_frozen": layer.is_frozen(),
                    "is_off": not layer.is_on()
                },
                "geometry": {}
            })

        # 3. Extract Graphical Geometries from Model Space and Paper Space (Layouts)
        entities = []
        counts = {
            "line": 0,
            "circle": 0,
            "arc": 0,
            "polyline": 0,
            "dimension": 0,
            "text": 0,
            "block": 0,
            "layer": len(layers)
        }

        # Identify active paperspace layout to see if we need viewport coordinate projection
        paperspace_layouts = [l for l in doc.layouts if l.name.lower() != 'model' and len(l) > 0]
        viewports = []
        active_layout = None
        for pl in paperspace_layouts:
            vp_candidates = [e for e in pl if e.dxftype() == "VIEWPORT" and e.dxf.id != 1]
            if vp_candidates:
                active_layout = pl
                viewports = vp_candidates
                break
        def project_point(x: float, y: float) -> tuple[float, float, float]:
            for vp in viewports:
                cx, cy = vp.dxf.center.x, vp.dxf.center.y
                w, h = vp.dxf.width, vp.dxf.height
                
                # Robustly query both view_target_point and view_center_point to find the true Model Space look-at center
                vc = vp.dxf.get('view_target_point')
                if not vc or (vc.x == 0.0 and vc.y == 0.0):
                    vc = vp.dxf.get('view_center_point')
                    
                vc_x, vc_y = (vc.x, vc.y) if vc else (0.0, 0.0)
                vh = vp.dxf.get('view_height')
                scale = h / vh if vh > 0 else 1.0
                
                half_mw = (w / scale) * 0.5
                half_mh = vh * 0.5
                
                if (vc_x - half_mw <= x <= vc_x + half_mw) and (vc_y - half_mh <= y <= vc_y + half_mh):
                    px = cx + (x - vc_x) * scale
                    py = cy + (y - vc_y) * scale
                    return px, py, scale
            if viewports:
                # Fallback to the first valid viewport if none matched
                vp = viewports[0]
                cx, cy = vp.dxf.center.x, vp.dxf.center.y
                
                # Robustly query both view_target_point and view_center_point for fallback viewport look-at center
                vc = vp.dxf.get('view_target_point')
                if not vc or (vc.x == 0.0 and vc.y == 0.0):
                    vc = vp.dxf.get('view_center_point')
                    
                vc_x, vc_y = (vc.x, vc.y) if vc else (0.0, 0.0)
                vh = vp.dxf.get('view_height')
                scale = h / vh if vh > 0 else 1.0
                px = cx + (x - vc_x) * scale
                py = cy + (y - vc_y) * scale
                return px, py, scale
            return x, y, 1.0

        def process_entity(entity, layout_name, depth=0, is_dimension=False):
            if depth > 10:
                logger.warning(f"Recursive block/dimension explosion depth limit reached at entity: {entity.dxftype()}")
                return

            dxftype = entity.dxftype()

            if dxftype == "INSERT":
                try:
                    for sub_ent in entity.virtual_entities():
                        process_entity(sub_ent, layout_name, depth + 1, is_dimension)
                except Exception as ex:
                    logger.debug(f"Could not explode block {getattr(entity.dxf, 'name', 'unknown')}: {ex}")

            mapped = EntityMapper.map_any(entity)
            if mapped:
                mapped["properties"]["layout_space"] = layout_name
                
                # Perform viewport projection if this entity belongs to Model space or is a dimension displayed in Paper space viewports
                if (layout_space_is_model := (layout_name.lower() == "model") or is_dimension) and viewports:
                    scale = 1.0
                    if mapped["entity_type"] == "line" and "geometry" in mapped:
                        geo = mapped["geometry"]
                        if "start" in geo and "end" in geo:
                            x1, y1, s = project_point(geo["start"][0], geo["start"][1])
                            geo["start"] = [x1, y1]
                            x2, y2, s = project_point(geo["end"][0], geo["end"][1])
                            geo["end"] = [x2, y2]
                            scale = s
                    elif mapped["entity_type"] in ("circle", "arc") and "geometry" in mapped:
                        geo = mapped["geometry"]
                        if "center" in geo:
                            cx, cy, s = project_point(geo["center"][0], geo["center"][1])
                            geo["center"] = [cx, cy]
                            geo["radius"] = geo.get("radius", 0.0) * s
                            scale = s
                    elif mapped["entity_type"] == "polyline" and "geometry" in mapped:
                        geo = mapped["geometry"]
                        if "vertices" in geo:
                            new_v = []
                            for pt in geo["vertices"]:
                                px, py, s = project_point(pt[0], pt[1])
                                new_v.append([px, py])
                                scale = s
                            geo["vertices"] = new_v
                        elif "points" in geo:
                            new_p = []
                            for pt in geo["points"]:
                                px, py, s = project_point(pt[0], pt[1])
                                new_p.append([px, py])
                                scale = s
                            geo["points"] = new_p
                    elif mapped["entity_type"] == "text" and "geometry" in mapped:
                        geo = mapped["geometry"]
                        # Project insert/location
                        if "location" in geo:
                            tx, ty, s = project_point(geo["location"][0], geo["location"][1])
                            geo["location"] = [tx, ty]
                            scale = s
                        if "insert" in geo:
                            tx, ty, s = project_point(geo["insert"][0], geo["insert"][1])
                            geo["insert"] = [tx, ty]
                            scale = s
                        if "text_point" in geo:
                            tx, ty, s = project_point(geo["text_point"][0], geo["text_point"][1])
                            geo["text_point"] = [tx, ty]
                            scale = s
                        
                        # Project bbox if present
                        props = mapped.get("properties", {})
                        if "bbox" in props and props["bbox"]:
                            try:
                                bbox = props["bbox"]
                                xmin, ymin, s = project_point(bbox[0][0], bbox[0][1])
                                xmax, ymax, s = project_point(bbox[1][0], bbox[1][1])
                                props["bbox"] = [[xmin, ymin], [xmax, ymax]]
                            except Exception:
                                pass
                    elif mapped["entity_type"] == "dimension" and "geometry" in mapped:
                        geo = mapped["geometry"]
                        if "def_point" in geo:
                            tx, ty, s = project_point(geo["def_point"][0], geo["def_point"][1])
                            geo["def_point"] = [tx, ty]
                            scale = s
                        if "text_point" in geo:
                            tx, ty, s = project_point(geo["text_point"][0], geo["text_point"][1])
                            geo["text_point"] = [tx, ty]
                            scale = s

                        
                        # Scale font size/height
                        props = mapped.get("properties", {})
                        if "height" in props:
                            props["height"] = props["height"] * scale
                        style = mapped.get("style", {})
                        if "fontSize" in style:
                            style["fontSize"] = style["fontSize"] * scale
                            
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
        }

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
