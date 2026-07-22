from typing import Any

from ..utils.text import strip_mtext


class EntityMapper:
    """
    Standardized mapper that translates raw ezdxf graphic entities
    into uniform serializable Python dictionaries with structure and geometry fields.
    """
    @staticmethod
    def map_line(entity: Any) -> dict[str, Any]:
        start = entity.dxf.start
        end = entity.dxf.end
        length = ((end[0] - start[0])**2 + (end[1] - start[1])**2 + (end[2] - start[2])**2)**0.5
        
        return {
            "entity_type": "line",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "length": length
            },
            "geometry": {
                "start": [start[0], start[1], start[2]],
                "end": [end[0], end[1], end[2]]
            }
        }

    @staticmethod
    def map_circle(entity: Any) -> dict[str, Any]:
        center = entity.dxf.center
        radius = entity.dxf.radius
        
        return {
            "entity_type": "circle",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "radius": radius
            },
            "geometry": {
                "center": [center[0], center[1], center[2]]
            }
        }

    @staticmethod
    def map_arc(entity: Any) -> dict[str, Any]:
        center = entity.dxf.center
        radius = entity.dxf.radius
        start_angle = entity.dxf.start_angle
        end_angle = entity.dxf.end_angle
        
        return {
            "entity_type": "arc",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "radius": radius,
                "start_angle": start_angle,
                "end_angle": end_angle
            },
            "geometry": {
                "center": [center[0], center[1], center[2]]
            }
        }

    @staticmethod
    def map_polyline(entity: Any) -> dict[str, Any]:
        points = []
        is_closed = entity.is_closed
        
        # Polyline can be lwpolyline or standard 3d polyline
        if entity.dxftype() == "LWPOLYLINE":
            for p in entity.get_points(format="xy"):
                points.append([p[0], p[1], 0.0])
        else:
            for p in entity.vertices:
                pt = p.dxf.location
                points.append([pt[0], pt[1], pt[2]])
                
        return {
            "entity_type": "polyline",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "vertex_count": len(points),
                "is_closed": is_closed
            },
            "geometry": {
                "points": points
            }
        }

    @staticmethod
    def map_dimension(entity: Any) -> dict[str, Any]:
        # Dimensions contain geometric definition points and overlay texts
        text = entity.dxf.text if hasattr(entity.dxf, "text") else ""
        measurement = entity.dxf.actual_measurement if hasattr(entity.dxf, "actual_measurement") else None

        if (not text or "<>" in text) and measurement is not None:
            meas_str = f"{measurement:.2f}".rstrip('0').rstrip('.')
            text = meas_str if not text else text.replace("<>", meas_str)

        text = EntityMapper._clean_mtext_content(text)

        def_point = entity.dxf.defpoint if hasattr(entity.dxf, "defpoint") else [0,0,0]
        text_point = entity.dxf.text_midpoint if hasattr(entity.dxf, "text_midpoint") else [0,0,0]
        if text_point[0] == 0 and text_point[1] == 0:
            text_point = def_point
        dim_type = entity.dxf.dimtype if hasattr(entity.dxf, "dimtype") else 0
        return {
            "entity_type": "dimension",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "text": text,
                "measurement": measurement,
                "dim_type": dim_type
            },
            "geometry": {
                "def_point": [def_point[0], def_point[1], def_point[2]],
                "text_point": [text_point[0], text_point[1], text_point[2]]
            }
        }

    @staticmethod
    def _clean_mtext_content(raw: str) -> str:
        """Thin alias for the shared canonical CAD text cleaner (utils/text.py's
        strip_mtext) so every entity mapper goes through one normalization path
        instead of a locally-duplicated, less-complete copy of the same logic.

        convert_symbols=False: this runs during extraction, BEFORE dxf_parser.py's
        transcode_value() re-encodes every string as latin-1 bytes and re-decodes as
        cp932 to recover real Shift-JIS text. Converting "%%c" to the real "Ø" symbol
        here would introduce a genuine Unicode character that transcode_value then
        corrupts (Ø's latin-1 byte 0xD8 decodes under cp932 as the replacement
        character). Downstream consumers reading already-stored/transcoded text
        (zone_detector, table_extractor, context_builder) call strip_mtext directly
        with its default (True) to get the real symbol -- see strip_mtext's docstring."""
        return strip_mtext(raw, convert_symbols=False)

    @staticmethod
    def map_text(entity: Any) -> dict[str, Any]:
        # Text/MText/Attributes maps literal strings
        dxftype = entity.dxftype()
        
        # 'text' attribute exists on MTEXT, ATTRIB, ATTDEF, whereas standard TEXT uses dxf.text
        if dxftype in ("MTEXT", "ATTRIB", "ATTDEF"):
            raw_content = entity.text if hasattr(entity, "text") else getattr(entity.dxf, "text", "")
        else:
            raw_content = entity.dxf.text if hasattr(entity.dxf, "text") else ""
            
        insert = entity.dxf.insert if hasattr(entity.dxf, "insert") else [0,0,0]
        height = entity.dxf.height if hasattr(entity.dxf, "height") else 2.5
        rotation = entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0.0

        # Clean MTEXT control codes and decode bytes if necessary
        text_content = EntityMapper._clean_mtext_content(raw_content) if raw_content else ""

        # Compute exact bounding box bounds in model space coordinates
        bbox_coords = None
        try:
            from ezdxf import bbox
            box = bbox.extents([entity])
            bbox_coords = [
                [float(box.extmin.x), float(box.extmin.y)],
                [float(box.extmax.x), float(box.extmax.y)]
            ]
        except Exception:
            pass

        # Alignments & attachment points
        halign = entity.dxf.halign if hasattr(entity.dxf, "halign") else 0
        valign = entity.dxf.valign if hasattr(entity.dxf, "valign") else 0
        attachment_point = entity.dxf.attachment_point if hasattr(entity.dxf, "attachment_point") else 0
        
        return {
            "entity_type": "text",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "text": text_content,
                "height": height,
                "is_multiline": dxftype == "MTEXT",
                "rotation": rotation,
                "halign": halign,
                "valign": valign,
                "attachment_point": attachment_point,
                "bbox": bbox_coords
            },
            "geometry": {
                "insert": [insert[0], insert[1], insert[2]]
            }
        }

    @staticmethod
    def map_block(entity: Any) -> dict[str, Any]:
        # INSERT entities represent block instances
        block_name = entity.dxf.name
        insert = entity.dxf.insert
        rotation = entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0.0
        
        attributes = {}
        if hasattr(entity, "attribs"):
            for attrib in entity.attribs:
                if hasattr(attrib.dxf, "tag") and hasattr(attrib.dxf, "text"):
                    # Clean MTEXT control codes and decode bytes if necessary
                    raw_content = attrib.text if hasattr(attrib, "text") else getattr(attrib.dxf, "text", "")
                    clean_text = EntityMapper._clean_mtext_content(raw_content) if raw_content else ""
                    attributes[attrib.dxf.tag] = clean_text
        
        return {
            "entity_type": "block",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "block_name": block_name,
                "rotation": rotation,
                "attributes": attributes
            },
            "geometry": {
                "insert": [insert[0], insert[1], insert[2]]
            }
        }

    @staticmethod
    def map_tolerance(entity: Any) -> dict[str, Any]:
        content = ""
        if hasattr(entity.dxf, "content") and entity.dxf.content:
            content = entity.dxf.content
        elif hasattr(entity.dxf, "text") and entity.dxf.text:
            content = entity.dxf.text
        # Deliberately NOT run through the generic MTEXT cleaner: GD&T tolerance
        # content commonly uses font-substitution codes like "{\Fgdt;j}" to render
        # a specific engineering symbol via a dedicated symbol font (the GDT.shx
        # style) -- the character itself ("j") is meaningless without that font
        # context, so stripping the \F code would silently corrupt the symbol's
        # meaning rather than merely reformat it (see test_gdt_welding_native_parsing).
        insert = entity.dxf.insert if hasattr(entity.dxf, "insert") else [0, 0, 0]
        
        return {
            "entity_type": "tolerance",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "text": content,
                "rotation": entity.dxf.get("rotation", 0.0) if hasattr(entity.dxf, "get") else 0.0,
            },
            "geometry": {
                "insert": [insert[0], insert[1], insert[2]]
            }
        }

    @staticmethod
    def map_leader(entity: Any) -> dict[str, Any]:
        vertices = []
        if hasattr(entity, "vertices"):
            vertices = [[v[0], v[1], v[2]] for v in entity.vertices]
        
        return {
            "entity_type": "leader",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "has_arrowhead": entity.dxf.get("has_arrowhead", 1) if hasattr(entity.dxf, "get") else 1
            },
            "geometry": {
                "vertices": vertices
            }
        }

    @staticmethod
    def map_multileader(entity: Any) -> dict[str, Any]:
        text = ""
        # MLeaderContext (entity.context) has no "text" attribute -- that check
        # always fails silently, so this used to fall through to entity.dxf.text
        # (rarely populated for MULTILEADER) and yield an empty string for most
        # annotations. get_mtext_content() is ezdxf's documented accessor; it
        # returns "" itself when the multileader has block content instead of
        # MTEXT, so no extra guard is needed.
        if hasattr(entity, "get_mtext_content"):
            text = entity.get_mtext_content() or ""
        if not text and hasattr(entity.dxf, "text"):
            text = entity.dxf.text
        text = EntityMapper._clean_mtext_content(text) if text else ""

        vertices = []
        # MultiLeaders are complex, we extract basic location/vertices if possible
        if hasattr(entity, "leaders"):
            for leader in entity.leaders:
                if hasattr(leader, "vertices"):
                    vertices.extend([[v[0], v[1], v[2]] for v in leader.vertices])
                    
        return {
            "entity_type": "multileader",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "text": text
            },
            "geometry": {
                "vertices": vertices,
                "insert": entity.dxf.insert if hasattr(entity.dxf, "insert") else [0, 0, 0]
            }
        }

    @staticmethod
    def map_hatch(entity: Any) -> dict[str, Any]:
        pattern_name = entity.dxf.pattern_name if hasattr(entity.dxf, "pattern_name") else "ANSI31"
        associative = entity.dxf.associativity if hasattr(entity.dxf, "associativity") else 0

        # Extract boundary paths (points)
        boundary_paths = []
        try:
            for path in entity.paths:
                if hasattr(path, "edges"):
                    for edge in path.edges:
                        if hasattr(edge, "start") and edge.start:
                            boundary_paths.append([edge.start[0], edge.start[1]])
        except Exception:
            pass

        return {
            "entity_type": "hatch",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "pattern_name": pattern_name,
                "is_solid": bool(entity.dxf.solid_fill) if hasattr(entity.dxf, "solid_fill") else False,
                "associative": bool(associative)
            },
            "geometry": {
                "boundary_points": boundary_paths[:20]  # Limit to 20 points to prevent DB bloating
            }
        }

    @classmethod
    def map_any(cls, entity: Any) -> dict[str, Any] | None:
        """
        Dynamically routes any standard ezdxf entity to its matching mapper.
        Returns mapped dictionary or None if type is not of interest.
        """
        if not hasattr(entity, "dxf") or not hasattr(entity.dxf, "handle"):
            return None
            
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                return cls.map_line(entity)
            elif dxftype == "CIRCLE":
                return cls.map_circle(entity)
            elif dxftype == "ARC":
                return cls.map_arc(entity)
            elif dxftype in ("POLYLINE", "LWPOLYLINE"):
                return cls.map_polyline(entity)
            elif dxftype == "DIMENSION":
                return cls.map_dimension(entity)
            elif dxftype == "TOLERANCE":
                return cls.map_tolerance(entity)
            elif dxftype == "LEADER":
                return cls.map_leader(entity)
            elif dxftype == "MULTILEADER":
                return cls.map_multileader(entity)
            elif dxftype == "HATCH":
                return cls.map_hatch(entity)
            elif dxftype in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
                return cls.map_text(entity)
            elif dxftype == "INSERT":
                return cls.map_block(entity)
        except Exception:
            # Shield drawing parsing from unhandled attribute failures inside corrupt entities
            return None
        return None
