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
            # 1. Let ezdxf auto-detect based on DXF header ($DWGCODEPAGE)
            doc = ezdxf.readfile(str(file_path))
            logger.info(f"DXF auto-detected encoding: {doc.encoding}")
        except (ezdxf.DXFError, UnicodeDecodeError):
            try:
                # 2. Force CP932 (Shift-JIS) for Japanese files that lack header codepages
                logger.info(f"Auto-detect failed. Trying CP932 (Shift-JIS) for: {file_path}")
                doc = ezdxf.readfile(str(file_path), encoding="cp932")
            except (ezdxf.DXFError, UnicodeDecodeError):
                try:
                    # 3. Force UTF-8
                    doc = ezdxf.readfile(str(file_path), encoding="utf-8")
                except (ezdxf.DXFError, UnicodeDecodeError):
                    try:
                        # 4. Latin-1 / ISO-8859-1 fallback
                        doc = ezdxf.readfile(str(file_path), encoding="latin-1")
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

        def process_entity(entity, layout_name, depth=0):
            if depth > 10:
                logger.warning(f"Recursive block/dimension explosion depth limit reached at entity: {entity.dxftype()}")
                return

            dxftype = entity.dxftype()
            if dxftype in ("INSERT", "DIMENSION"):
                try:
                    # ezdxf's explode() decomposes INSERT blocks and DIMENSIONS into standard primitives (lines, text, arcs)
                    # positioned and rotated correctly in world coordinates, then destroys the source compound entity.
                    exploded_query = entity.explode()
                    for child in exploded_query:
                        process_entity(child, layout_name, depth + 1)
                    return
                except Exception as explode_err:
                    logger.warning(f"Unable to explode legacys complex {dxftype} entity: {str(explode_err)}")
                    # Fallback to normal mapping if explode fails
                    pass

            mapped = EntityMapper.map_any(entity)
            if mapped:
                mapped["properties"]["layout_space"] = layout_name
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

        duration = time.time() - start_time
        logger.info(
            f"Successfully parsed DXF in {duration:.4f}s. "
            f"Extracted {len(entities)} elements across {len(layers)} layers."
        )

        return entities, layers, counts, metadata
