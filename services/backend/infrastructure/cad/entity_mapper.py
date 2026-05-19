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
    def map_text(entity: Any) -> Dict[str, Any]:
        # Text/MText maps literal strings
        dxftype = entity.dxftype()
        text_content = entity.text if dxftype == "MTEXT" else entity.dxf.text
        insert = entity.dxf.insert if hasattr(entity.dxf, "insert") else [0,0,0]
        height = entity.dxf.height if hasattr(entity.dxf, "height") else 2.5
        
        return {
            "entity_type": "text",
            "layer": entity.dxf.layer,
            "properties": {
                "handle": entity.dxf.handle,
                "color": entity.dxf.color,
                "text": text_content,
                "height": height,
                "is_multiline": dxftype == "MTEXT"
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
            elif dxftype in ("TEXT", "MTEXT"):
                return cls.map_text(entity)
            elif dxftype == "INSERT":
                return cls.map_block(entity)
        except Exception:
            # Shield drawing parsing from unhandled attribute failures inside corrupt entities
            return None
        return None
