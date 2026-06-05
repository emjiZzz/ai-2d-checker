from typing import Any, Dict

class EntityMapper:
    """
    Standardized mapper that translates raw ezdxf graphic entities
    into uniform serializable Python dictionaries with structure and geometry fields.
    """
    @staticmethod
    def map_line(entity: Any) -> Dict[str, Any]:
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
    def map_circle(entity: Any) -> Dict[str, Any]:
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
    def map_arc(entity: Any) -> Dict[str, Any]:
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
    def map_polyline(entity: Any) -> Dict[str, Any]:
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
    def map_dimension(entity: Any) -> Dict[str, Any]:
        # Dimensions contain geometric definition points and overlay texts
        text = entity.dxf.text if hasattr(entity.dxf, "text") else ""
        measurement = entity.dxf.actual_measurement if hasattr(entity.dxf, "actual_measurement") else None
        def_point = entity.dxf.defpoint if hasattr(entity.dxf, "defpoint") else [0,0,0]
        text_point = entity.dxf.text_midpoint if hasattr(entity.dxf, "text_midpoint") else [0,0,0]
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
        """
        Strip MTEXT rich-text formatting control codes from CAD text entities.
        AutoCAD MTEXT uses codes like:
          \\W0.8;   = width factor
          \\H2.5;   = height
          \\A1;     = alignment (0=bottom, 1=center, 2=top)
          \\T0.5;   = tracking/character spacing
          \\S ...;  = stacked fractions
          \\P       = paragraph break
          \\~       = non-breaking space
          {{\\...}} = font/color change groups
        """
        import re
        if not raw:
            return raw

        # Handle bytes (cp932 encoded Japanese text from legacy DXF files)
        if isinstance(raw, bytes):
            for enc in ('utf-8', 'cp932', 'latin-1'):
                try:
                    raw = raw.decode(enc)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            else:
                raw = raw.decode('utf-8', errors='replace')

        # Strip MTEXT format codes: \X...; or \X patterns
        text = re.sub(r'\\[WwHhAaTtQqFfCcLlOoKkPpNn][^;]*;', '', raw)
        # Strip \P paragraph breaks
        text = re.sub(r'\\[Pp]', ' ', text)
        # Strip \~ non-breaking spaces
        text = text.replace('\\~', ' ')
        # Strip stacked fraction blocks \S...^...;
        text = re.sub(r'\\S[^;]*;', '', text)
        # Strip curly-brace groups for font/color changes { }
        text = re.sub(r'[{}]', '', text)
        # Strip remaining single backslash escapes
        text = re.sub(r'\\(.)', r'\1', text)
        return text.strip()

    @staticmethod
    def map_text(entity: Any) -> Dict[str, Any]:
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
    def map_block(entity: Any) -> Dict[str, Any]:
        # INSERT entities represent block instances
        block_name = entity.dxf.name
        insert = entity.dxf.insert
        rotation = entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0.0
        
        return {
            "entity_type": "block",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "block_name": block_name,
                "rotation": rotation
            },
            "geometry": {
                "insert": [insert[0], insert[1], insert[2]]
            }
        }

    @staticmethod
    def map_tolerance(entity: Any) -> Dict[str, Any]:
        content = ""
        if hasattr(entity.dxf, "content") and entity.dxf.content:
            content = entity.dxf.content
        elif hasattr(entity.dxf, "text") and entity.dxf.text:
            content = entity.dxf.text
        insert = entity.dxf.insert if hasattr(entity.dxf, "insert") else [0, 0, 0]
        
        return {
            "entity_type": "text",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "text": content,
                "height": 2.5,
                "is_multiline": False,
                "rotation": 0.0,
                "halign": 1,
                "valign": 1,
                "attachment_point": 0
            },
            "geometry": {
                "insert": [insert[0], insert[1], insert[2]]
            }
        }

    @classmethod
    def map_any(cls, entity: Any) -> Dict[str, Any] | None:
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
            elif dxftype in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
                return cls.map_text(entity)
            elif dxftype == "INSERT":
                return cls.map_block(entity)
        except Exception:
            # Shield drawing parsing from unhandled attribute failures inside corrupt entities
            return None
        return None
