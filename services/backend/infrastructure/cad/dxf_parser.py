import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
import ezdxf
from ...logger import logger
from ...core.security import validate_sandboxed_path
from .entity_mapper import EntityMapper

class DXFParser:
    """
    Parses a DXF file using ezdxf, extracting layers, geometry, dimensions, blocks,
    and metadata inside a secure path sandbox.
    """
    def parse_file(self, file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int], Dict[str, Any]]:
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
        if paperspace_layouts:
            active_layout = paperspace_layouts[0]
            # Retrieve all non-initial viewport entities
            viewports = [e for e in active_layout if e.dxftype() == "VIEWPORT" and e.dxf.id != 1]

        def project_point(x: float, y: float) -> Tuple[float, float, float]:
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
            if dxftype in ("INSERT", "DIMENSION", "TOLERANCE", "LEADER", "MULTILEADER"):
                try:
                    if dxftype == "INSERT" and hasattr(entity, "attribs"):
                        for attrib in entity.attribs:
                            process_entity(attrib, layout_name, depth + 1)
                            
                    # ezdxf's explode() decomposes INSERT blocks, DIMENSIONS, and GD&T/welding symbols into standard primitives (lines, text, arcs)
                    # positioned and rotated correctly in world coordinates, then destroys the source compound entity.
                    exploded_query = entity.explode()
                    for child in exploded_query:
                        process_entity(child, layout_name, depth + 1, is_dimension=is_dimension or (dxftype in ("DIMENSION", "TOLERANCE", "LEADER", "MULTILEADER")))
                    return
                except Exception as explode_err:
                    logger.warning(f"Unable to explode legacys complex {dxftype} entity: {str(explode_err)}")
                    # Fallback to normal mapping if explode fails
                    pass

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
                        
                        # Project bbox if present
                        props = mapped.get("properties", {})
                        if "bbox" in props and props["bbox"]:
                            try:
                                bbox = props["bbox"]
                                xmin, ymin, s = project_point(bbox[0][0], bbox[0][1])
                                xmax, ymax, s = project_point(bbox[1][0], bbox[1][1])
                                props["bbox"] = [[xmin, ymin], [xmax, ymax]]
                                scale = s
                            except Exception:
                                pass
                        
                        # Scale font size/height
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

        # 4. Extract standard metadata headers
        metadata = {
            "ezdxf_version": ezdxf.__version__,
            "acad_version": doc.acad_release,
            "handseed": doc.header.get("$HANDSEED", "unknown"),
            "measurement": doc.header.get("$MEASUREMENT", -1), # 0 = Inch, 1 = Metric
            "extmin": list(doc.header.get("$EXTMIN", [0, 0, 0])),
            "extmax": list(doc.header.get("$EXTMAX", [0, 0, 0])),
        }

        # Transcode all string elements in layers and entities to their correct drawing encoding
        doc_encoding = getattr(doc, "encoding", "cp932") or "cp932"
        # Normalize to lower standard
        if doc_encoding.lower() in ("ansi_932", "cp932", "ms932", "shift_jis", "sjis"):
            doc_encoding = "cp932"
        
        logger.info(f"Performing deep CJK transcoding using drawing encoding: {doc_encoding}")
        
        def transcode_value(val: Any) -> Any:
            if isinstance(val, str):
                val_clean = val
                val_clean = val_clean.replace('\uff97', 'x')
                val_clean = val_clean.replace('\u30e9', 'x')
                val_clean = val_clean.replace('×', 'x')
                val_clean = val_clean.replace('ラ', 'x')
                try:
                    b = val_clean.encode('latin1')
                except Exception:
                    return val_clean
                for enc in (doc_encoding, 'cp932', 'utf-8', 'latin-1'):
                    if not enc:
                        continue
                    try:
                        decoded = b.decode(enc)
                        decoded = decoded.replace('\uff97', 'x')
                        decoded = decoded.replace('\u30e9', 'x')
                        decoded = decoded.replace('×', 'x')
                        decoded = decoded.replace('ラ', 'x')
                        return decoded
                    except Exception:
                        continue
                return b.decode('utf-8', errors='replace').replace('\uff97', 'x').replace('\u30e9', 'x').replace('×', 'x').replace('ラ', 'x')
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
