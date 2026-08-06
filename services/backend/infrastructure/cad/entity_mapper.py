import math
import re
from typing import Any

from ..utils.text import strip_mtext

# DXF sentinel lineweights. -1/-2/-3 are BYLAYER/BYBLOCK/DEFAULT rather than real
# widths; anything >= 0 is a width in 1/100 mm.
LINEWEIGHT_BYLAYER = -1
LINEWEIGHT_BYBLOCK = -2
LINEWEIGHT_DEFAULT = -3

# Number of segments used to tessellate a hatch boundary arc/ellipse edge. Hatch
# boundaries are fill outlines, not visible geometry, so a coarse approximation is
# fine and keeps the stored document small.
ARC_TESSELLATION_SEGMENTS = 16

# Number of segments used to tessellate an ELLIPSE into a polyline approximation.
# Higher than ARC_TESSELLATION_SEGMENTS because an ellipse here is visible model
# geometry that gets bounded, compared and rendered, not a fill outline.
ELLIPSE_TESSELLATION_SEGMENTS = 48

# Max chord deviation (drawing units) when reducing a SPLINE to a polyline.
SPLINE_FLATTENING_DISTANCE = 0.05

# Declarative description of which geometry keys hold coordinates, so that the
# model->paper viewport projection can be applied uniformly to every entity type
# instead of a hand-written per-type branch that silently skipped half of them
# (hatch, tolerance, leader, multileader and block were never projected).
#
#   points            -- a single [x, y(, z)] coordinate
#   point_lists       -- a flat list of coordinates
#   point_list_groups -- a list of lists of coordinates (e.g. hatch island paths)
#   lengths           -- scalar distances in drawing units that scale with the viewport
#   vectors           -- a direction+magnitude offset from the entity's own origin.
#                        Scaled but NOT translated: projecting an ellipse's major axis
#                        as if it were a point would move it to the viewport origin and
#                        silently reshape the ellipse.
#
# See `viewport_transform.py` and `dxf_parser.project_mapped_entity`.
GEOMETRY_SCHEMA: dict[str, dict[str, tuple[str, ...]]] = {
    "line": {"points": ("start", "end")},
    "circle": {"points": ("center",), "lengths": ("radius",)},
    "arc": {"points": ("center",), "lengths": ("radius",)},
    "polyline": {"point_lists": ("points", "vertices")},
    "ellipse": {
        "points": ("center",),
        "point_lists": ("points",),
        "vectors": ("major_axis",),
    },
    "spline": {"point_lists": ("control_points", "fit_points", "points")},
    "dimension": {
        "points": ("def_point", "text_point", "ext1_point", "ext2_point"),
    },
    "text": {"points": ("insert", "location", "text_point")},
    "block": {"points": ("insert",)},
    "tolerance": {"points": ("insert",)},
    "leader": {"point_lists": ("vertices",)},
    "multileader": {"points": ("insert",), "point_lists": ("vertices",)},
    "hatch": {"point_lists": ("boundary_points",), "point_list_groups": ("paths",)},
}

# Property keys holding drawing-unit sizes that must scale with the viewport.
# `width_factor` and `tracking` are deliberately absent: they are dimensionless
# multipliers, not lengths, and scaling them would compound with the geometry scale.
SCALED_PROPERTY_KEYS: tuple[str, ...] = ("height", "radius", "text_height", "column_width")


def _dxf_get(dxf: Any, name: str, default: Any = None) -> Any:
    """Read a DXF attribute tolerantly.

    ezdxf namespaces expose `.get(name, default)`, but it returns the default for
    attributes that are merely unset even when the entity type defines a meaningful
    fallback (an unset `lineweight` is BYLAYER, not "missing"). Test doubles are
    plain objects with neither `.get` nor the full attribute set, so fall through to
    `getattr` and finally the caller's default.
    """
    try:
        getter = getattr(dxf, "get", None)
        if callable(getter):
            value = getter(name, None)
            if value is not None:
                return value
    except Exception:
        pass
    try:
        value = getattr(dxf, name, None)
    except Exception:
        return default
    return default if value is None else value


def _as_xy(point: Any, default: tuple[float, float] = (0.0, 0.0)) -> list[float]:
    """Coerce an ezdxf vector / tuple / list into a plain [x, y] list."""
    try:
        if point is None:
            return [default[0], default[1]]
        if hasattr(point, "x") and hasattr(point, "y"):
            return [float(point.x), float(point.y)]
        return [float(point[0]), float(point[1])]
    except Exception:
        return [default[0], default[1]]


def _as_xyz(point: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    try:
        if point is None:
            return list(default)
        if hasattr(point, "x") and hasattr(point, "y"):
            return [float(point.x), float(point.y), float(getattr(point, "z", 0.0) or 0.0)]
        z = float(point[2]) if len(point) > 2 else 0.0
        return [float(point[0]), float(point[1]), z]
    except Exception:
        return list(default)


def common_properties(entity: Any) -> dict[str, Any]:
    """Presentation attributes shared by every graphic entity.

    `lineweight` and `linetype` are the reason this exists: `geometry_serializer.py`
    has always read them, but no mapper ever wrote them, so every stroke resolved to
    width 1.0 and dashes never applied -- which renders hidden and centre lines as
    solid. On a mechanical drawing that is a semantic error, not a cosmetic one.
    """
    dxf = getattr(entity, "dxf", None)
    if dxf is None:
        return {}

    props: dict[str, Any] = {
        "handle": _dxf_get(dxf, "handle", ""),
        "color": _dxf_get(dxf, "color", 256),
        "linetype": _dxf_get(dxf, "linetype", "BYLAYER"),
        "lineweight": _dxf_get(dxf, "lineweight", LINEWEIGHT_BYLAYER),
        "ltscale": _dxf_get(dxf, "ltscale", 1.0),
    }

    # true_color and transparency are optional DXF attributes absent on most
    # entities; only record them when actually present so consumers can tell
    # "inherits from layer" apart from "explicitly set".
    true_color = _dxf_get(dxf, "true_color", None)
    if true_color is not None:
        try:
            props["true_color"] = int(true_color)
        except Exception:
            pass

    transparency = _dxf_get(dxf, "transparency", None)
    if transparency is not None:
        try:
            props["transparency"] = float(transparency)
        except Exception:
            pass

    return props


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

        props = common_properties(entity)
        props["length"] = length

        return {
            "entity_type": "line",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "start": [start[0], start[1], start[2]],
                "end": [end[0], end[1], end[2]]
            }
        }

    @staticmethod
    def map_circle(entity: Any) -> dict[str, Any]:
        center = entity.dxf.center
        radius = entity.dxf.radius

        props = common_properties(entity)
        props["radius"] = radius

        return {
            "entity_type": "circle",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "center": [center[0], center[1], center[2]],
                # Mirrored into geometry so the viewport projection scales one
                # canonical value; `properties.radius` is kept in step by
                # SCALED_PROPERTY_KEYS for consumers that read it there.
                "radius": radius
            }
        }

    @staticmethod
    def map_arc(entity: Any) -> dict[str, Any]:
        center = entity.dxf.center
        radius = entity.dxf.radius
        start_angle = entity.dxf.start_angle
        end_angle = entity.dxf.end_angle

        props = common_properties(entity)
        props["radius"] = radius
        props["start_angle"] = start_angle
        props["end_angle"] = end_angle

        return {
            "entity_type": "arc",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "center": [center[0], center[1], center[2]],
                "radius": radius
            }
        }

    @staticmethod
    def _tessellate_ellipse(
        center: list[float], major_axis: list[float], ratio: float,
        start_param: float, end_param: float,
    ) -> list[list[float]]:
        """Sample the DXF ellipse parametric form into a polyline.

        DXF stores an ellipse as centre + major-axis *vector* + minor/major `ratio`,
        swept between two parameters. The minor axis is the major axis rotated 90
        degrees and scaled by `ratio`, so a point at parameter t is
        `center + major*cos(t) + minor*sin(t)`. Computed directly rather than via
        ezdxf's own flattening so that plain test doubles (and entities detached from
        a document) tessellate identically to real ones.
        """
        try:
            cx, cy = float(center[0]), float(center[1])
            mx, my = float(major_axis[0]), float(major_axis[1])
            # minor axis = major rotated +90 degrees, scaled by ratio
            nx, ny = -my * ratio, mx * ratio

            sweep = end_param - start_param
            if abs(sweep) < 1e-12:
                sweep = math.tau

            steps = max(8, ELLIPSE_TESSELLATION_SEGMENTS)
            points = []
            for i in range(steps + 1):
                t = start_param + sweep * (i / steps)
                cos_t, sin_t = math.cos(t), math.sin(t)
                points.append([cx + mx * cos_t + nx * sin_t, cy + my * cos_t + ny * sin_t])
            return points
        except Exception:
            return []

    @staticmethod
    def map_ellipse(entity: Any) -> dict[str, Any]:
        """ELLIPSE -> native parameters plus a tessellated outline.

        Kept as its own `entity_type` rather than degraded into a polyline because the
        *presence* of an ellipse is diagnostic, not just decorative: a circle viewed at
        an angle projects to an ellipse, so ellipse density is what separates an
        axonometric (isometric) view from an orthographic one, which keeps its circles
        as CIRCLE/ARC. `zone_detector._detect_iso_zone` reads exactly that signal, and
        flattening ellipses to polylines here would erase it.

        Before this existed, `map_any` had no ELLIPSE branch and returned None, so every
        ellipse was dropped at ingestion -- 111 of them across the 6-drawing corpus, all
        on the three drawings that carry an isometric view (90% of one such view's
        entities). See docs/vault/06 - .../Gotcha - Dropped ELLIPSE & SPLINE Geometry.
        """
        center = _as_xyz(entity.dxf.center)
        major_axis = _as_xyz(_dxf_get(entity.dxf, "major_axis", (1.0, 0.0, 0.0)))
        ratio = float(_dxf_get(entity.dxf, "ratio", 1.0))
        start_param = float(_dxf_get(entity.dxf, "start_param", 0.0))
        end_param = float(_dxf_get(entity.dxf, "end_param", math.tau))

        props = common_properties(entity)
        props.update({
            "ratio": ratio,
            "start_param": start_param,
            "end_param": end_param,
            "is_closed": abs((end_param - start_param) - math.tau) < 1e-9,
        })

        return {
            "entity_type": "ellipse",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "center": center,
                # A vector from `center`, not an absolute coordinate -- see the
                # "vectors" note on GEOMETRY_SCHEMA.
                "major_axis": major_axis,
                "points": EntityMapper._tessellate_ellipse(
                    center, major_axis, ratio, start_param, end_param
                ),
            },
        }

    @staticmethod
    def map_spline(entity: Any) -> dict[str, Any]:
        """SPLINE -> control/fit points plus a flattened outline.

        Like ELLIPSE, previously dropped entirely by `map_any` (46 across the corpus,
        concentrated in isometric views, where curved silhouette edges are splines).
        `flattening` is ezdxf's adaptive sampler and needs a live document; control
        points are the fallback when it is unavailable, which is coarse but keeps the
        entity locatable and boundable rather than absent.
        """
        control_points: list[list[float]] = []
        fit_points: list[list[float]] = []
        try:
            control_points = [_as_xyz(p) for p in (entity.control_points or [])]
        except Exception:
            control_points = []
        try:
            fit_points = [_as_xyz(p) for p in (entity.fit_points or [])]
        except Exception:
            fit_points = []

        points: list[list[float]] = []
        try:
            points = [
                [float(p[0]), float(p[1])]
                for p in entity.flattening(SPLINE_FLATTENING_DISTANCE)
            ]
        except Exception:
            points = [[p[0], p[1]] for p in (fit_points or control_points)]

        props = common_properties(entity)
        props.update({
            "degree": int(_dxf_get(entity.dxf, "degree", 3)),
            "is_closed": bool(_dxf_get(entity.dxf, "closed", False)),
            "control_point_count": len(control_points),
        })

        return {
            "entity_type": "spline",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "control_points": control_points,
                "fit_points": fit_points,
                "points": points,
            },
        }

    @staticmethod
    def map_polyline(entity: Any) -> dict[str, Any]:
        points = []
        is_closed = entity.is_closed

        # Polyline can be lwpolyline or standard 3d polyline
        if entity.dxftype() == "LWPOLYLINE":
            # An LWPOLYLINE is planar by definition, but that plane is not necessarily
            # z=0: the entity stores its height once, in `dxf.elevation`, instead of
            # repeating it per vertex. Reading `format="xy"` and hardcoding 0.0 flattened
            # every LWPOLYLINE onto the origin plane -- which reads as correct on the 2D
            # canvas and is wrong everywhere else.
            elevation = float(_dxf_get(entity.dxf, "elevation", 0.0) or 0.0)
            for p in entity.get_points(format="xy"):
                points.append([p[0], p[1], elevation])
        else:
            for p in entity.vertices:
                pt = p.dxf.location
                points.append([pt[0], pt[1], pt[2]])

        props = common_properties(entity)
        props["vertex_count"] = len(points)
        props["is_closed"] = is_closed

        return {
            "entity_type": "polyline",
            "layer": entity.dxf.layer,
            "properties": props,
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

        def_point = _dxf_get(entity.dxf, "defpoint", None)
        text_point = _dxf_get(entity.dxf, "text_midpoint", None)
        def_xyz = _as_xyz(def_point)
        text_xyz = _as_xyz(text_point)
        if text_xyz[0] == 0 and text_xyz[1] == 0:
            text_xyz = list(def_xyz)

        dim_type = _dxf_get(entity.dxf, "dimtype", 0)

        props = common_properties(entity)
        props["text"] = text
        props["measurement"] = measurement
        props["dim_type"] = dim_type
        # dimstyle drives arrowhead size, text height, extension-line offsets and
        # gap -- everything needed to draw the dimension rather than just anchor it.
        props["dimstyle"] = _dxf_get(entity.dxf, "dimstyle", "")
        props["rotation"] = _dxf_get(entity.dxf, "angle", 0.0)

        geometry: dict[str, Any] = {
            "def_point": def_xyz,
            "text_point": text_xyz,
        }

        # defpoint2/defpoint3 are the extension-line origins -- the two measured
        # features. Without them a dimension can only be pinned to a point; with
        # them it can actually be drawn and its span reasoned about.
        ext1 = _dxf_get(entity.dxf, "defpoint2", None)
        ext2 = _dxf_get(entity.dxf, "defpoint3", None)
        if ext1 is not None:
            geometry["ext1_point"] = _as_xyz(ext1)
        if ext2 is not None:
            geometry["ext2_point"] = _as_xyz(ext2)

        return {
            "entity_type": "dimension",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": geometry
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
    def _parse_mtext_formatting(raw: str) -> tuple[float, float]:
        """Pull the width factor (\\W) and tracking (\\T) out of raw MTEXT content.

        Returns (width_factor, tracking), defaulting to (1.0, 1.0). These codes are
        stripped by `strip_mtext` during cleaning, but they carry the horizontal scaling
        the drawing actually specifies, so they are captured before that happens.
        """
        width_factor, tracking = 1.0, 1.0
        if not raw:
            return width_factor, tracking
        for code, setter in (("W", "w"), ("T", "t")):
            match = re.search(r"\\" + code + r"([0-9]*\.?[0-9]+)\s*;", raw)
            if match:
                try:
                    value = float(match.group(1))
                    if value > 0:
                        if setter == "w":
                            width_factor = value
                        else:
                            tracking = value
                except ValueError:
                    pass
        return width_factor, tracking

    @staticmethod
    def _estimate_text_bbox(
        insert: list[float], text: str, height: float, rotation: float
    ) -> list[list[float]] | None:
        """Approximate a text bounding box from font metrics.

        Used when `ezdxf.bbox.extents()` cannot measure the entity (missing font,
        unresolved style, or a virtual entity with no owning document). Downstream
        text placement in the vector renderer needs *a* box far more than it needs a
        perfect one, and a silent `None` forces every consumer to invent its own
        fallback.

        The 0.6 advance-width ratio is a latin-font approximation. At this point in
        the pipeline CJK strings are still cp932 bytes held in a latin-1 str -- one
        full-width glyph is two chars here -- so 2 x 0.6 lands near the 1.0 em a
        full-width glyph actually occupies. Rotation is handled by taking the
        axis-aligned envelope of the rotated box.
        """
        if not text or height <= 0:
            return None
        try:
            width = len(text) * height * 0.6
            x, y = float(insert[0]), float(insert[1])
            corners = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
            if rotation:
                rad = math.radians(rotation)
                cos_r, sin_r = math.cos(rad), math.sin(rad)
                corners = [(cx * cos_r - cy * sin_r, cx * sin_r + cy * cos_r) for cx, cy in corners]
            xs = [x + cx for cx, _ in corners]
            ys = [y + cy for _, cy in corners]
            return [[min(xs), min(ys)], [max(xs), max(ys)]]
        except Exception:
            return None

    @staticmethod
    def map_text(entity: Any) -> dict[str, Any]:
        # Text/MText/Attributes maps literal strings
        dxftype = entity.dxftype()

        # 'text' attribute exists on MTEXT, ATTRIB, ATTDEF, whereas standard TEXT uses dxf.text
        if dxftype in ("MTEXT", "ATTRIB", "ATTDEF"):
            raw_content = entity.text if hasattr(entity, "text") else getattr(entity.dxf, "text", "")
        else:
            raw_content = entity.dxf.text if hasattr(entity.dxf, "text") else ""

        insert = entity.dxf.insert if hasattr(entity.dxf, "insert") else [0, 0, 0]

        # MTEXT has no `height` attribute -- its size lives in `char_height`, and
        # ezdxf *raises* DXFAttributeError for `height` rather than returning a default,
        # so a `hasattr(entity.dxf, "height")` guard silently reports False and every
        # MTEXT falls through to the fallback. On a real customer drawing carrying 16
        # distinct text heights (1.75-10.0), that stored 2.5 for 246 of 252 MTEXT
        # entities: text size was effectively not extracted at all.
        if dxftype == "MTEXT":
            height = _dxf_get(entity.dxf, "char_height", 0.0) or 2.5
        else:
            height = _dxf_get(entity.dxf, "height", 0.0) or 2.5
        rotation = entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0.0

        # Inline MTEXT formatting the cleaner is about to strip. \W is a horizontal
        # width factor and \T is letter tracking -- between them they are how the file
        # says "render this string squashed to 0.87x". Discarding them and then trying
        # to recover the same information from the bounding box is the wrong way round.
        width_factor, tracking = EntityMapper._parse_mtext_formatting(raw_content)

        # Clean MTEXT control codes and decode bytes if necessary
        text_content = EntityMapper._clean_mtext_content(raw_content) if raw_content else ""

        insert_xyz = _as_xyz(insert)

        # The MTEXT column width, when one is defined. This is the wrap width, and it is
        # also what ezdxf reports as the bounding box -- see the bbox_source note below.
        column_width = float(_dxf_get(entity.dxf, "width", 0.0) or 0.0) if dxftype == "MTEXT" else 0.0

        # Bounding box in model space.
        #
        # IMPORTANT: for MTEXT, `ezdxf.bbox.extents()` returns the declared *column box*,
        # not the ink extent of the glyphs. Measured on a real customer drawing, 228 of
        # 232 MTEXT bounding boxes were exactly equal to the declared column width, with
        # the ratio of natural glyph width to box width ranging from 0.13 to 3.56. So a
        # box is not a target to scale text into -- doing so would stretch or squash
        # strings to arbitrary column widths. `bbox_source` records which kind of box
        # this is so consumers cannot conflate them.
        bbox_coords = None
        bbox_source = "none"
        try:
            from ezdxf import bbox
            box = bbox.extents([entity])
            bbox_coords = [
                [float(box.extmin.x), float(box.extmin.y)],
                [float(box.extmax.x), float(box.extmax.y)]
            ]
            width = bbox_coords[1][0] - bbox_coords[0][0]
            is_column_box = column_width > 0 and abs(width - column_width) < 1e-6
            bbox_source = "mtext_column" if is_column_box else "ezdxf"
        except Exception:
            bbox_coords = None

        if bbox_coords is None:
            bbox_coords = EntityMapper._estimate_text_bbox(
                insert_xyz, text_content, float(height or 0.0), float(rotation or 0.0)
            )
            bbox_source = "estimated" if bbox_coords else "none"

        # Alignments & attachment points
        halign = entity.dxf.halign if hasattr(entity.dxf, "halign") else 0
        valign = entity.dxf.valign if hasattr(entity.dxf, "valign") else 0
        attachment_point = entity.dxf.attachment_point if hasattr(entity.dxf, "attachment_point") else 0

        props = common_properties(entity)
        props.update({
            "text": text_content,
            "height": height,
            "is_multiline": dxftype == "MTEXT",
            "rotation": rotation,
            "halign": halign,
            "valign": valign,
            "attachment_point": attachment_point,
            "bbox": bbox_coords,
            "bbox_source": bbox_source,
            "style": _dxf_get(entity.dxf, "style", ""),
            "source_dxftype": dxftype,
            # Horizontal glyph scaling and letter tracking the drawing specifies
            # directly -- the correct inputs for placing this string, in place of
            # inferring a scale from the bounding box.
            "width_factor": width_factor,
            "tracking": tracking,
            "column_width": column_width,
        })

        return {
            "entity_type": "text",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "insert": insert_xyz
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

        props = common_properties(entity)
        props.update({
            "block_name": block_name,
            "rotation": rotation,
            "attributes": attributes,
            "xscale": _dxf_get(entity.dxf, "xscale", 1.0),
            "yscale": _dxf_get(entity.dxf, "yscale", 1.0),
            # An INSERT is a container: its drawable content is stored separately as
            # exploded child entities carrying `parent_handle`. Renderers should draw
            # the children and treat this record as grouping metadata (it is also the
            # only carrier of title-block ATTRIB values, which `virtual_entities()`
            # does not yield).
            "is_container": True,
        })

        return {
            "entity_type": "block",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "insert": _as_xyz(insert)
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

        props = common_properties(entity)
        props["text"] = content
        props["rotation"] = _dxf_get(entity.dxf, "rotation", 0.0)

        return {
            "entity_type": "tolerance",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "insert": _as_xyz(insert)
            }
        }

    @staticmethod
    def map_leader(entity: Any) -> dict[str, Any]:
        vertices = []
        if hasattr(entity, "vertices"):
            vertices = [_as_xyz(v) for v in entity.vertices]

        props = common_properties(entity)
        props["has_arrowhead"] = _dxf_get(entity.dxf, "has_arrowhead", 1)
        props["dimstyle"] = _dxf_get(entity.dxf, "dimstyle", "")

        return {
            "entity_type": "leader",
            "layer": entity.dxf.layer,
            "properties": props,
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
                    vertices.extend([_as_xyz(v) for v in leader.vertices])

        props = common_properties(entity)
        props["text"] = text

        return {
            "entity_type": "multileader",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                "vertices": vertices,
                "insert": _as_xyz(_dxf_get(entity.dxf, "insert", None))
            }
        }

    @staticmethod
    def _tessellate_arc_edge(
        center: list[float], radius: float, start_angle: float, end_angle: float, ccw: bool = True
    ) -> list[list[float]]:
        """Approximate a hatch boundary arc edge as a short polyline."""
        try:
            start = math.radians(start_angle)
            end = math.radians(end_angle)
            if ccw:
                while end <= start:
                    end += 2 * math.pi
            else:
                while end >= start:
                    end -= 2 * math.pi
            steps = max(2, ARC_TESSELLATION_SEGMENTS)
            return [
                [
                    center[0] + radius * math.cos(start + (end - start) * i / steps),
                    center[1] + radius * math.sin(start + (end - start) * i / steps),
                ]
                for i in range(steps + 1)
            ]
        except Exception:
            return []

    @classmethod
    def _extract_hatch_paths(cls, entity: Any) -> list[list[list[float]]]:
        """Extract hatch boundaries as closed point loops, one per island path.

        The previous implementation collected only `edge.start` from edge paths,
        capped at 20 points and flattened across all paths, which produced an open,
        truncated, island-less outline -- enough to locate a hatch, not enough to
        fill one. Polyline paths (the common case) were skipped entirely because
        they expose `.vertices` rather than `.edges`.
        """
        paths: list[list[list[float]]] = []
        try:
            entity_paths = entity.paths
        except Exception:
            return paths

        for path in entity_paths:
            loop: list[list[float]] = []

            vertices = getattr(path, "vertices", None)
            if vertices is not None:
                # PolylinePath: vertices are (x, y, bulge); bulge (arc segments) is
                # approximated as a straight chord.
                try:
                    loop = [[float(v[0]), float(v[1])] for v in vertices]
                except Exception:
                    loop = []
            else:
                edges = getattr(path, "edges", None)
                if edges is None:
                    continue
                for edge in edges:
                    edge_type = type(edge).__name__
                    try:
                        if edge_type == "ArcEdge":
                            loop.extend(cls._tessellate_arc_edge(
                                _as_xy(getattr(edge, "center", None)),
                                float(getattr(edge, "radius", 0.0) or 0.0),
                                float(getattr(edge, "start_angle", 0.0) or 0.0),
                                float(getattr(edge, "end_angle", 0.0) or 0.0),
                                bool(getattr(edge, "ccw", True)),
                            ))
                        elif edge_type == "EllipseEdge":
                            # Approximated by its major-axis circle; hatch outlines
                            # are fill boundaries, so this is visually adequate.
                            center = _as_xy(getattr(edge, "center", None))
                            major = _as_xy(getattr(edge, "major_axis", None), (1.0, 0.0))
                            radius = math.hypot(major[0], major[1])
                            loop.extend(cls._tessellate_arc_edge(
                                center, radius,
                                float(getattr(edge, "start_param", 0.0) or 0.0),
                                float(getattr(edge, "end_param", 360.0) or 360.0),
                                bool(getattr(edge, "ccw", True)),
                            ))
                        elif edge_type == "SplineEdge":
                            control_points = getattr(edge, "control_points", None) or []
                            loop.extend([_as_xy(p) for p in control_points])
                        else:
                            # LineEdge and anything unrecognised: use its endpoints.
                            start = getattr(edge, "start", None)
                            end = getattr(edge, "end", None)
                            if start is not None:
                                loop.append(_as_xy(start))
                            if end is not None:
                                loop.append(_as_xy(end))
                    except Exception:
                        continue

            if len(loop) < 2:
                continue

            # Close the loop so consumers can fill it without guessing.
            if loop[0] != loop[-1]:
                loop.append(list(loop[0]))
            paths.append(loop)

        return paths

    @classmethod
    def map_hatch(cls, entity: Any) -> dict[str, Any]:
        pattern_name = entity.dxf.pattern_name if hasattr(entity.dxf, "pattern_name") else "ANSI31"
        associative = entity.dxf.associativity if hasattr(entity.dxf, "associativity") else 0

        paths = cls._extract_hatch_paths(entity)

        props = common_properties(entity)
        props.update({
            "pattern_name": pattern_name,
            "is_solid": bool(entity.dxf.solid_fill) if hasattr(entity.dxf, "solid_fill") else False,
            "associative": bool(associative),
            "pattern_scale": _dxf_get(entity.dxf, "pattern_scale", 1.0),
            "pattern_angle": _dxf_get(entity.dxf, "pattern_angle", 0.0),
            "path_count": len(paths),
        })

        return {
            "entity_type": "hatch",
            "layer": entity.dxf.layer,
            "properties": props,
            "geometry": {
                # Closed loops, one per island. `boundary_points` is retained as a
                # flattened view for existing consumers that expect a single list.
                "paths": paths,
                "boundary_points": [pt for loop in paths for pt in loop],
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
            elif dxftype == "ELLIPSE":
                return cls.map_ellipse(entity)
            elif dxftype == "SPLINE":
                return cls.map_spline(entity)
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
