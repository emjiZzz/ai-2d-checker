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
        # `render_text_point` is the block's own text anchor, offset off the dimension line;
        # `text_point` is `text_midpoint`, which sits on it. Both are projected — the renderer
        # prefers the former, and the comparison keeps reading the latter, so entity pooling and
        # every cached audit are untouched. Same split as `render_text` vs `text`.
        "points": ("def_point", "text_point", "ext1_point", "ext2_point", "render_text_point"),
        # The flattened contents of the dimension's anonymous geometry block. Listed here
        # so the model->paper projection reaches them for free; a dimension whose anchors
        # were projected but whose rendered lines were not would draw its measurement in
        # one place and its arrows in another.
        "point_list_groups": ("render_paths", "render_fills"),
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
SCALED_PROPERTY_KEYS: tuple[str, ...] = (
    "height", "radius", "text_height", "column_width", "arrow_size",
)

#: DXF's own default for DIMASZ, used when a leader names a dimstyle the file does not define.
_DEFAULT_DIMASZ = 2.5

# Tessellation density for curved dimension geometry (radial, diameter and angular
# dimensions render as arcs). A full circle at this density is well under a pixel of
# chord error at any zoom the review canvas reaches.
_DIM_ARC_SEGMENTS = 32

#: A filled region needs three distinct corners; below that there is nothing to paint.
_MIN_FILL_VERTICES = 3


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


def _dxf_is_set(dxf: Any, name: str) -> bool:
    """True only when the DXF actually CARRIES this attribute.

    Distinct from reading it: ezdxf returns the DXF-spec default for an unset optional
    attribute, so an absent `has_hookline` reads back as `1` and an absent `text_width` as
    `1` — both truthy, neither written by the CAD. Anything that branches on "did the file
    say this" has to ask here first; `_dxf_get` answers the different question of "what is
    the effective value", and the two disagree exactly where it matters.
    """
    try:
        checker = getattr(dxf, "hasattr", None)
        return bool(checker(name)) if callable(checker) else False
    except Exception:
        return False


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


def _degree_sign_in_doc_bytes(entity: Any) -> str:
    """A degree sign in the BYTE domain this mapper actually works in.

    ⚠ `entity_mapper` runs **before** `dxf_parser.transcode_value`. The DXF is read with
    `encoding="latin-1"` so bytes survive intact, which means every string here is raw
    document-codepage bytes with one character per byte -- see the header note in
    `infrastructure/utils/text.py`. Emitting a real U+00B0 therefore inserts the single byte
    0xB0, and the later transcode decodes that byte in the document's codepage: under CP932
    0xB0 is `ｰ`, the halfwidth katakana prolonged sound mark. A 60-degree dimension came
    back reading `60ｰ`.

    So the sign is encoded to the document's own codepage first and handed over as latin-1
    characters -- i.e. exactly the bytes the DXF would have contained had it spelled the value
    itself. CP932 gives 0x81 0x8B, which transcodes back to U+00B0; a UTF-8 document gives
    0xC2 0xB0, which also transcodes back. Neither byte collides with the MTEXT markup
    characters (0x5C, 0x7B, 0x7D, 0x7E) that `_clean_mtext_content` strips.

    Falls back to CP932, matching `transcode_value`'s own first fallback, when the document
    declares no usable encoding.
    """
    enc = getattr(getattr(entity, "doc", None), "encoding", None) or "cp932"
    try:
        return "°".encode(enc).decode("latin-1")
    except (LookupError, UnicodeError):
        return "°".encode("cp932").decode("latin-1")


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

            # A DXF elliptical arc always sweeps COUNTER-CLOCKWISE from start_param to
            # end_param, so `end < start` means it wraps through 2pi -- not that it runs
            # backwards. Taking the raw difference sweeps the short way round instead,
            # drawing the arc on the WRONG SIDE of its own ellipse: it lands on top of
            # arcs that are already there and leaves the half it should have covered
            # empty. On this corpus 9 of 33 isometric arcs wrap (`start=180 end=0`,
            # `start=225 end=0`), which is why the flange rendered as a broken crescent
            # while ezdxf's own renderer drew closed rings from the same entities.
            #
            # The wrap only appears AFTER block explosion -- the block definitions store
            # (180, 360), and the INSERT transform is what rewrites it to (180, 0). So
            # reading the source blocks looks fine and the defect only shows up in the
            # exploded geometry that actually gets rendered.
            sweep = end_param - start_param
            if sweep <= 1e-12:
                sweep += math.tau

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
            # Normalised the same way `_tessellate_ellipse` normalises its sweep, so a
            # wrapped full ellipse (start == end, or end < start summing to a full turn)
            # is not reported as an open arc.
            "is_closed": abs(((end_param - start_param) % math.tau)) < 1e-9,
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
            for p in entity.get_points(format="xy"):
                points.append([p[0], p[1], 0.0])
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
    def _dimension_render_geometry(entity: Any) -> dict[str, Any]:
        """Flatten a DIMENSION's rendered block into drawable primitives.

        A DIMENSION carries anchors (`defpoint`, `text_midpoint`, `defpoint2/3`), a
        `measurement` and a `dimstyle` -- and nothing drawable. The dimension line,
        the extension lines and the arrowheads live in an anonymous block that ezdxf
        exposes via `virtual_entities()`. Without flattening it, a vector renderer draws
        a dimension as literally nothing, which is what happened: switching `renderMode`
        to 'vector' produced a sharp sheet with every dimension silently deleted.

        Returned as geometry to attach to the DIMENSION itself rather than as sibling
        entities, and that distinction is load-bearing. `context_builder` pools
        `entity_type == 'text'` and `entity_type == 'dimension'` separately, so exploding
        a dimension into real LINE/TEXT entities the way INSERT is exploded would make
        every dimension appear *twice* in the audit -- once as a dimension carrying
        `measurement`, once as text carrying the same string. Keeping the geometry
        attached leaves the comparison entity set byte-identical.

        TEXT/MTEXT children are deliberately not emitted: the measurement string is
        already on the dimension. Their *height* and *rotation* are harvested, because
        those are the values resolved through the dimstyle, which the DIMENSION entity
        does not itself carry.
        """
        paths: list[list[list[float]]] = []
        fills: list[list[list[float]]] = []
        text_meta: dict[str, Any] = {}

        def add_arc(cx: float, cy: float, r: float, a0: float, a1: float) -> None:
            if r <= 0:
                return
            if a1 <= a0:
                a1 += 360.0
            sweep = a1 - a0
            steps = max(4, min(_DIM_ARC_SEGMENTS, int(_DIM_ARC_SEGMENTS * sweep / 360.0) + 2))
            paths.append([
                [cx + r * math.cos(math.radians(a0 + sweep * i / steps)),
                 cy + r * math.sin(math.radians(a0 + sweep * i / steps))]
                for i in range(steps + 1)
            ])

        def flatten(src: Any, depth: int) -> None:
            if depth > 4:
                return
            try:
                children = list(src.virtual_entities())
            except Exception:
                return
            for e in children:
                try:
                    t = e.dxftype()
                    if t == "LINE":
                        paths.append([_as_xy(e.dxf.start), _as_xy(e.dxf.end)])
                    elif t == "LWPOLYLINE":
                        pts = [[float(p[0]), float(p[1])] for p in e.get_points("xy")]
                        if len(pts) >= 2:
                            if getattr(e, "closed", False):
                                pts.append(list(pts[0]))
                            paths.append(pts)
                    elif t == "POLYLINE":
                        pts = [_as_xy(v.dxf.location) for v in e.vertices]
                        if len(pts) >= 2:
                            if getattr(e, "is_closed", False):
                                pts.append(list(pts[0]))
                            paths.append(pts)
                    elif t == "ARC":
                        c = _as_xy(e.dxf.center)
                        add_arc(c[0], c[1], float(e.dxf.radius),
                                float(_dxf_get(e.dxf, "start_angle", 0.0) or 0.0),
                                float(_dxf_get(e.dxf, "end_angle", 0.0) or 0.0))
                    elif t == "CIRCLE":
                        c = _as_xy(e.dxf.center)
                        add_arc(c[0], c[1], float(e.dxf.radius), 0.0, 360.0)
                    elif t in ("SOLID", "TRACE"):
                        # Arrowheads. The DXF quad order is vtx0, vtx1, vtx3, vtx2 --
                        # reading them in numeric order draws a bowtie, not a triangle.
                        # A triangular SOLID repeats its last corner (vtx2 == vtx3), which
                        # that order lands side by side, so collapsing runs of coincident
                        # vertices covers the degenerate case without a second rule for it.
                        corners = [
                            _as_xy(e.dxf.vtx0), _as_xy(e.dxf.vtx1),
                            _as_xy(e.dxf.vtx3), _as_xy(e.dxf.vtx2),
                        ]
                        distinct: list[list[float]] = []
                        for corner in corners:
                            if not distinct or corner != distinct[-1]:
                                distinct.append(corner)
                        if len(distinct) >= _MIN_FILL_VERTICES:
                            fills.append(distinct)
                    elif t == "HATCH":
                        for p in getattr(e, "paths", []):
                            pts = [[float(v[0]), float(v[1])] for v in getattr(p, "vertices", [])]
                            if len(pts) >= _MIN_FILL_VERTICES:
                                fills.append(pts)
                    elif t == "INSERT":
                        # Arrowheads are blocks under most dimstyles (such as _OPEN30).
                        # Flattening recurses into the block so its constituent lines
                        # (e.g. open arrow barbs) are added directly to paths.
                        flatten(e, depth + 1)
                    elif t in ("TEXT", "MTEXT", "ATTRIB") and not text_meta:
                        height = _dxf_get(e.dxf, "char_height", 0.0) or _dxf_get(e.dxf, "height", 0.0)
                        if height:
                            text_meta["text_height"] = float(height)

                        # WHERE the block puts the measurement, which is not where the
                        # DIMENSION's own `text_midpoint` puts it.
                        #
                        # `text_midpoint` sits ON the dimension line -- it is the line's
                        # midpoint, not the text's. The CAD offsets the text perpendicular to
                        # the line by `text_height/2 + DIMGAP` so it reads BESIDE the line, and
                        # only the block records that. Measured on M745221N01's revision, model
                        # units: the phi145 line is at x -105.70 and its MTEXT at -110.02, phi100
                        # at -93.80 against -98.06, and the horizontal `6` at y -439.05 against
                        # -434.79. A uniform ~4.3 offset that anchoring on `text_midpoint`
                        # discards, drawing every measurement straight through its own dimension
                        # line -- which is what the canvas did, and what iCAD SX does not.
                        #
                        # Harvested rather than recomputed from height and DIMGAP: the offset is
                        # only *approximately* uniform (4.32 / 4.25 / 4.26 on one sheet), the
                        # side depends on the text direction, and a leader-style radial dimension
                        # places its text differently again. The authored point is exact and free.
                        insert = _dxf_get(e.dxf, "insert", None)
                        if insert is not None:
                            text_meta["render_text_point"] = _as_xyz(insert)

                        # The string the block ACTUALLY renders, which is not the same as the
                        # one `map_dimension` reconstructs from `actual_measurement`.
                        #
                        # On this corpus `dimpost` is empty and `dimension.dxf.text` is only
                        # '\W0.8;\T0.875;<>' -- the diameter prefix lives here, in the rendered
                        # block: '\W0.800000;\T0.875000;%%c145'. Rebuilding the text from the
                        # measurement therefore drops it, and 3 of the 4 dimensions on
                        # M745221N01 showed "145" where iCAD SX shows "φ145". The same applies
                        # to any suffix, tolerance stack or unit formatting the dimstyle bakes
                        # into the block.
                        #
                        # Stored as `render_text`, NOT by overwriting `properties["text"]`.
                        # `context_builder` pools dimensions into the comparison entity set by
                        # that field, so changing it would alter every cached audit and force a
                        # COMPARISON_CACHE_VERSION bump. Same reasoning as attaching the
                        # geometry here instead of exploding it into siblings.
                        raw_render_text = e.text if hasattr(e, "text") else _dxf_get(e.dxf, "text", "")
                        if raw_render_text:
                            cleaned = EntityMapper._clean_mtext_content(raw_render_text)
                            if cleaned:
                                text_meta["render_text"] = cleaned
                            # \W and \T live on the block's MTEXT, never on the DIMENSION, so
                            # this is the only place a dimension's horizontal scaling can be
                            # recovered.
                            wf, tr = EntityMapper._parse_mtext_formatting(raw_render_text)
                            text_meta["width_factor"] = wf
                            text_meta["tracking"] = tr

                            # Stacked tolerances: \S<upper>^<lower>;
                            # In CAD (iCAD SX / DXF standard), dimension tolerances are formatted
                            # as stacked fractions with a caret divider (\S+0.4^ +0.2;).
                            tol_match = re.search(r"\\S([^^;]*)\^([^;]*);", raw_render_text)
                            if tol_match:
                                u = tol_match.group(1).strip()
                                l = tol_match.group(2).strip()
                                if u or l:
                                    text_meta["tolerance_upper"] = u
                                    text_meta["tolerance_lower"] = l
                        # MTEXT keeps its orientation in `text_direction` (a vector), not in
                        # `rotation` -- which reads None here and silently degrades to 0, so
                        # every rotated dimension drew its value horizontally. On this corpus
                        # that put the vertical 145 and 100 on top of each other, 8.5 units
                        # apart, because both are 90-degree dimensions whose text is meant to
                        # run vertically. `get_rotation()` resolves the vector (and returns
                        # the plain rotation when there is no direction vector).
                        #
                        # Same family as the documented `map_text` MTEXT trap: reading the
                        # TEXT-shaped attribute off an MTEXT yields a wrong-but-plausible
                        # default rather than an error.
                        rotation = None
                        if t == "MTEXT":
                            try:
                                rotation = float(e.get_rotation())
                            except Exception:
                                rotation = None
                        if rotation is None:
                            rotation = float(_dxf_get(e.dxf, "rotation", 0.0) or 0.0)
                        text_meta["text_rotation"] = rotation

                        # The rendered text carries its OWN colour, routinely different from
                        # the dimension's: on this corpus every DIMENSION is ACI 3 (green) while
                        # its measurement MTEXT is ACI 2 (yellow). Painting the text in the
                        # dimension's stroke colour turns every measurement green, which is not
                        # what the drawing says. Stored as the raw ACI index so the serializer
                        # resolves BYLAYER/BYBLOCK through the same path as every other stroke.
                        text_color = _dxf_get(e.dxf, "color", None)
                        if text_color is not None:
                            try:
                                text_meta["text_color_index"] = int(text_color)
                            except (TypeError, ValueError):
                                pass
                except Exception:
                    continue

        flatten(entity, 0)
        return {"paths": paths, "fills": fills, "text": text_meta}

    @staticmethod
    def map_dimension(entity: Any) -> dict[str, Any]:
        # Dimensions contain geometric definition points and overlay texts
        text = entity.dxf.text if hasattr(entity.dxf, "text") else ""
        measurement = entity.dxf.actual_measurement if hasattr(entity.dxf, "actual_measurement") else None
        dim_type = _dxf_get(entity.dxf, "dimtype", 0)
        # Low 3 bits carry the KIND; the high bits are flags. Same mask as
        # `spatial_differ._dimension_key`, which keys on this rather than on display text.
        dim_kind = int(dim_type or 0) & 0b111

        if (not text or "<>" in text) and measurement is not None:
            # ⚠ `actual_measurement` is RADIANS for an angular dimension (kinds 2 and 5) and
            # drawing units for every other kind. Formatting it blindly stored a 60° dimension
            # as `1.05` and an 80° one as `1.4` -- a value that appears nowhere on the sheet.
            #
            # It failed silently for two reasons. The deterministic engine keys dimensions on
            # `measurement` + kind and never reads this string, so comparison was unaffected;
            # and on a linear dimension the substitution is correct, which is most of them.
            # It surfaced only when the manual-check overlay started showing the stored text to
            # a human, who could see the drawing said `60°` -- and by then `EntityAddress.text`
            # had been capturing the same wrong string into ground truth.
            if dim_kind in (2, 5):
                deg = f"{math.degrees(measurement):.2f}".rstrip('0').rstrip('.')
                meas_str = deg + _degree_sign_in_doc_bytes(entity)
            else:
                meas_str = f"{measurement:.2f}".rstrip('0').rstrip('.')
            text = meas_str if not text else text.replace("<>", meas_str)

        text = EntityMapper._clean_mtext_content(text)

        def_point = _dxf_get(entity.dxf, "defpoint", None)
        text_point = _dxf_get(entity.dxf, "text_midpoint", None)
        def_xyz = _as_xyz(def_point)
        text_xyz = _as_xyz(text_point)
        if text_xyz[0] == 0 and text_xyz[1] == 0:
            text_xyz = list(def_xyz)

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

        # The drawable half. See `_dimension_render_geometry` for why this attaches to the
        # dimension instead of being exploded into sibling entities.
        rendered = EntityMapper._dimension_render_geometry(entity)
        if rendered["paths"]:
            geometry["render_paths"] = rendered["paths"]
        if rendered["fills"]:
            geometry["render_fills"] = rendered["fills"]
        props.update(rendered["text"])

        # Fallback: if MTEXT did not carry stacked \S codes, check dimtol/dimtp/dimtm overrides
        if "tolerance_upper" not in props and hasattr(entity, "dxf"):
            try:
                dimtol = _dxf_get(entity.dxf, "dimtol", 0)
                if dimtol:
                    tp = _dxf_get(entity.dxf, "dimtp", None)
                    tm = _dxf_get(entity.dxf, "dimtm", None)
                    if tp is not None or tm is not None:
                        props["tolerance_upper"] = f"+{tp}" if tp and tp > 0 else (str(tp) if tp is not None else "")
                        props["tolerance_lower"] = f"-{tm}" if tm and tm > 0 else (str(-tm) if tm is not None else "")
            except Exception:
                pass

        # Lives in geometry, not properties, so the model->paper projection reaches it through
        # the schema's `points` tuple. A text anchor left in properties would stay in model
        # coordinates and place the measurement off the sheet entirely.
        render_text_point = props.pop("render_text_point", None)
        if render_text_point is not None:
            geometry["render_text_point"] = render_text_point

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
        # MTEXT keeps its orientation in the `text_direction` VECTOR, not in `rotation` --
        # `dxf.rotation` reads 0.0 for a string that is actually vertical, which is a
        # wrong-but-plausible default rather than an error. Measured on M745221N01: the two
        # vertical tolerance-table headers ("Standard", "Job No.") carry
        # `text_direction=(0,1,0)` with `dxf.rotation=0`, so both drew horizontally and ran
        # across the neighbouring cells.
        #
        # This is the same trap as the `char_height` case above, and the same one already
        # fixed inside `_dimension_render_geometry` for dimension text -- reading the
        # TEXT-shaped attribute off an MTEXT silently degrades. `get_rotation()` resolves the
        # vector and falls back to the plain rotation when there is no direction vector.
        rotation = 0.0
        if dxftype == "MTEXT":
            try:
                rotation = float(entity.get_rotation())
            except Exception:
                rotation = float(_dxf_get(entity.dxf, "rotation", 0.0) or 0.0)
        else:
            rotation = float(_dxf_get(entity.dxf, "rotation", 0.0) or 0.0)

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
        # Effective value, not presence: the DXF default for `has_arrowhead` is 1 (enabled), and
        # that IS the right reading for a leader that stays silent — unlike `has_hookline` below,
        # where the default is a landing the CAD never asked for.
        props["has_arrowhead"] = _dxf_get(entity.dxf, "has_arrowhead", 1)
        style_name = _dxf_get(entity.dxf, "dimstyle", "")
        props["dimstyle"] = style_name

        # A LEADER carries no arrowhead geometry — the size lives on the DIMSTYLE it names, as
        # DIMASZ. Without it the pointer is a bare line that stops at the feature, which reads as
        # a leader that never arrives; ezdxf records two extra primitives at the tip that we drew
        # none of. Stored as a length so the viewport projection scales it with everything else.
        #
        # ⚠ ezdxf draws this arrow at ~1.5x DIMASZ (measured: its recorded tip box solves to a
        # triangle 3.75 long against DIMASZ 2.5 on this sheet). That multiplier is not documented
        # anywhere we could find, so DIMASZ is used raw rather than fitted to one renderer — a
        # slightly small arrow is a size difference, no arrow is a missing feature.
        arrow_size = 0.0
        try:
            doc = getattr(entity, "doc", None)
            if doc is not None and style_name and style_name in doc.dimstyles:
                arrow_size = float(_dxf_get(doc.dimstyles.get(style_name).dxf, "dimasz", 0.0) or 0.0)
        except Exception:
            arrow_size = 0.0
        props["arrow_size"] = arrow_size or _DEFAULT_DIMASZ

        # The hookline -- the landing segment that runs under the annotation text -- is NOT in
        # the vertex list. A LEADER stores its path plus two flags, and the renderer is expected
        # to extend the final segment by `text_width` so the line reaches the text it points
        # from. Without it a callout's pointer stops in mid-air short of its own label.
        #
        # Measured on M745221N01's `6-9キリ` callout: our chain ended at paper x 125.0 while
        # ezdxf's own rendering of the same leader reaches 107.9 -- **17.1 units short**, which
        # is the entire landing. `text_width` is 22.62 model units (16.16 projected), so
        # extending by it lands at 108.8, within ~1 unit of ezdxf. The residual is the dimstyle
        # gap ezdxf also adds; it is left out because reading DIMGAP here to chase one unit
        # costs more than it buys, and being 1 unit short of the text beats being 17.
        # Both must be PRESENT, not merely readable. ezdxf hands back the DXF-spec defaults for
        # unset optionals — `has_hookline` reads 1 and `text_width` reads 1 on a leader that
        # declares neither — so reading them would extend every plain leader by a phantom unit.
        # Measured: this file's two section-callout tails carry neither attribute and were
        # lengthened by exactly 1.0 before the presence check went in.
        has_hookline = _dxf_is_set(entity.dxf, "has_hookline") and _dxf_get(entity.dxf, "has_hookline", 0)
        text_width = (
            _dxf_get(entity.dxf, "text_width", 0.0) if _dxf_is_set(entity.dxf, "text_width") else 0.0
        )
        props["has_hookline"] = bool(has_hookline)
        props["text_width"] = text_width
        # `text_width` UNDER-STATES the annotation. On M745221N01's revision the leader declares
        # 22.62 while the MTEXT it points from is 28.56 wide — 5.94 short, which leaves the
        # landing ending inside the text instead of spanning it. The leader also carries
        # `annotation_handle`, a hard reference to that very MTEXT, so the real width is one
        # lookup away; `text_width` is only the fallback for a leader that names no annotation.
        #
        # This deliberately OVERSHOOTS ezdxf, which uses `text_width` and lands 4.2 units short
        # of the text. The evidence for the longer landing is the reference sheet of the same
        # pair: it has no hookline and instead authors its landing as an explicit LINE, 27.9
        # units against a 29.0-wide text — i.e. the CAD's own landing spans its annotation. Our
        # ezdxf-agreement checks cover text placement and the entity census, neither of which
        # this touches.
        annotation_width = 0.0
        if _dxf_is_set(entity.dxf, "annotation_handle"):
            try:
                doc = getattr(entity, "doc", None)
                target = doc.entitydb.get(_dxf_get(entity.dxf, "annotation_handle", None)) if doc else None
                if target is not None and target.dxftype() == "MTEXT":
                    annotation_width = float(_dxf_get(target.dxf, "width", 0.0) or 0.0)
            except Exception:
                annotation_width = 0.0

        landing = annotation_width or text_width
        props["landing_width"] = landing
        if has_hookline and landing and len(vertices) >= 2:
            tail_from, tail_to = vertices[-2], vertices[-1]
            dx = tail_to[0] - tail_from[0]
            dy = tail_to[1] - tail_from[1]
            span = math.hypot(dx, dy)
            if span > 0:
                width = float(landing)
                vertices.append([
                    tail_to[0] + dx / span * width,
                    tail_to[1] + dy / span * width,
                    tail_to[2] if len(tail_to) > 2 else 0.0,
                ])

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
