from typing import Any

from ...domain.models.extracted_entity import ExtractedEntity
from ...logger import logger

try:
    from ezdxf.colors import aci2rgb
except Exception:  # pragma: no cover - ezdxf is a hard dependency; never fail a render on it
    aci2rgb = None  # type: ignore[assignment]


# DXF colour sentinels. Neither of these is a colour: both are instructions to go and
# look somewhere else, which is exactly what the old `COLOR_MAP.get(index, "#FFFFFF")`
# did not do.
ACI_BYBLOCK = 0
ACI_BYLAYER = 256

# DXF lineweight sentinels. Like the ACI ones above, none of these is a width: each says "go
# and look somewhere else". Flattening them to a number is how every inheriting entity ended up
# 0.01mm thick.
LINEWEIGHT_BYLAYER = -1
LINEWEIGHT_BYBLOCK = -2
LINEWEIGHT_DEFAULT = -3

#: $LWDEFAULT, the width an entity gets when everything above resolves to DEFAULT.
DEFAULT_LINEWEIGHT_MM = 0.25

# The canvas this feeds is dark, and ACI 7 and 250 mean "black on white paper".
# Rendering them literally paints black on near-black. The raster path got this for free
# from ezdxf's `ColorPolicy.COLOR_SWAP_BW`; the vector path has to do it itself, or
# switching `renderMode` to 'vector' silently loses every ACI 7 entity -- which on a
# typical mechanical drawing is most of them.
_DARK_CANVAS_LUMA_FLOOR = 40

# Linetype names that should render dashed. Matched as substrings because DXF linetype
# names are per-file and decorated in practice (HIDDEN2, CENTERX2, DASHDOT2, JIS_02W...),
# so equality against a two-item list matched almost nothing. Rendering a centre or
# hidden line as solid is a semantic error on a mechanical drawing, not a cosmetic one.
_DASHED_LINETYPE_HINTS = ("dash", "hidden", "center", "centre", "phantom", "divide", "dot")


class GeometrySerializer:
    """
    Serializes backend ExtractedEntity documents into normalized,
    frontend-ready JSON payloads for the review canvas.
    Handles color mapping, lineweight scaling, and layer grouping.
    """

    # Fallback palette, used only when ezdxf's real ACI table is unavailable. ezdxf ships
    # the authoritative 256-entry palette (`aci2rgb`), so prefer it: this table stops at 9
    # and every index above it collapsed to white, which is wrong for any drawing using
    # the 10-249 colour cube.
    COLOR_MAP = {
        0: "#FFFFFF",  # ByBlock
        1: "#FF0000",  # Red
        2: "#FFFF00",  # Yellow
        3: "#00FF00",  # Green
        4: "#00FFFF",  # Cyan
        5: "#0000FF",  # Blue
        6: "#FF00FF",  # Magenta
        7: "#FFFFFF",  # White/Black
        8: "#808080",  # Dark Grey
        9: "#C0C0C0",  # Light Grey
        256: "#FFFFFF"  # ByLayer fallback
    }

    @staticmethod
    def _for_dark_canvas(r: int, g: int, b: int) -> str:
        """Hex string for an RGB triple, lifting near-black to white."""
        if (r * 299 + g * 587 + b * 114) / 1000 < _DARK_CANVAS_LUMA_FLOOR:
            return "#FFFFFF"
        return f"#{r:02X}{g:02X}{b:02X}"

    @classmethod
    def _aci_to_hex(cls, index: int) -> str:
        if aci2rgb is not None:
            try:
                rgb = aci2rgb(int(index))
                return cls._for_dark_canvas(int(rgb.r), int(rgb.g), int(rgb.b))
            except Exception:
                pass
        return cls.COLOR_MAP.get(index, "#FFFFFF")

    @staticmethod
    def _build_layer_colors(entities: list[ExtractedEntity]) -> dict[str, int]:
        """Layer name -> ACI index, from the `layer` records in the same entity set.

        `dxf_parser` stores each layer table entry as an entity with
        `entity_type == "layer"`, so no extra query is needed. A negative colour means
        the layer is switched off in the DXF; the magnitude is still the colour.
        """
        colors: dict[str, int] = {}
        for ent in entities:
            if (ent.entity_type or "").lower() != "layer":
                continue
            raw = ent.properties.get("color", ACI_BYLAYER)
            try:
                colors[ent.layer] = abs(int(raw))
            except (TypeError, ValueError):
                continue
        return colors

    @staticmethod
    def _build_layer_lineweights(entities: list[ExtractedEntity]) -> dict[str, int]:
        """Layer name -> lineweight enum, from the `layer` records in the same entity set."""
        weights: dict[str, int] = {}
        for ent in entities:
            if (ent.entity_type or "").lower() != "layer":
                continue
            try:
                weights[ent.layer] = int(ent.properties.get("lineweight", LINEWEIGHT_DEFAULT))
            except (TypeError, ValueError):
                continue
        return weights

    @staticmethod
    def _resolve_lineweight(ent: ExtractedEntity, layer_lineweights: dict[str, int]) -> float:
        """Stroke width in MILLIMETRES for one entity.

        BYLAYER (-1) and BYBLOCK (-2) are sentinels, not widths, and DEFAULT (-3) means "use
        $LWDEFAULT". The old code flattened all three to 1.0 and then divided by 100, so every
        inheriting entity came out at 0.01mm -- below the hairline floor at any zoom, i.e. the
        thinnest possible line. That is the same defect the colour path already documents for
        ACI 256: a sentinel resolved as though it were a value.
        """
        try:
            raw = int(ent.properties.get("lineweight", LINEWEIGHT_BYLAYER))
        except (TypeError, ValueError):
            raw = LINEWEIGHT_BYLAYER

        if raw in (LINEWEIGHT_BYLAYER, LINEWEIGHT_BYBLOCK):
            try:
                raw = int(layer_lineweights.get(ent.layer, LINEWEIGHT_DEFAULT))
            except (TypeError, ValueError):
                raw = LINEWEIGHT_DEFAULT

        if raw < 0:
            # Still a sentinel (DEFAULT, or a layer that is itself BYLAYER). $LWDEFAULT is
            # 0.25mm in every DXF this corpus has produced.
            return DEFAULT_LINEWEIGHT_MM

        # DXF lineweight is an enum in 1/100 mm (25 == 0.25mm), so it always divides by 100.
        return round(raw / 100.0, 4)

    @classmethod
    def _resolve_stroke(cls, ent: ExtractedEntity, layer_colors: dict[str, int]) -> str:
        """Final stroke colour for one entity.

        Precedence mirrors DXF: an explicit 24-bit `true_color` outranks the ACI index,
        and the BYLAYER/BYBLOCK sentinels defer to the owning layer. The old code did
        neither, so every BYLAYER entity -- the overwhelming majority on a real drawing --
        resolved to flat white and the drawing lost all of its colour coding the moment
        anything rendered vectors.

        BYBLOCK properly resolves against the owning INSERT rather than the layer. The
        parent is recoverable (`parent_handle`), but exploded children already carry the
        layer they landed on, so deferring to the layer is both cheaper and right in the
        common case where a block's contents are BYLAYER anyway.
        """
        true_color = ent.properties.get("true_color")
        if true_color is not None:
            try:
                tc = int(true_color)
                return cls._for_dark_canvas((tc >> 16) & 0xFF, (tc >> 8) & 0xFF, tc & 0xFF)
            except (TypeError, ValueError):
                pass

        try:
            index = int(ent.properties.get("color", ACI_BYLAYER))
        except (TypeError, ValueError):
            index = ACI_BYLAYER

        return cls._resolve_index(index, ent.layer, layer_colors)

    @classmethod
    def _resolve_index(cls, index: int, layer: str, layer_colors: dict[str, int]) -> str:
        """Resolve one ACI index against a layer, honouring the BYLAYER/BYBLOCK sentinels."""
        if index in (ACI_BYLAYER, ACI_BYBLOCK):
            index = layer_colors.get(layer, 7)
        return cls._aci_to_hex(index)

    @staticmethod
    def _is_dashed(linetype: Any) -> bool:
        name = str(linetype or "").lower()
        if name in ("", "bylayer", "byblock", "continuous"):
            return False
        return any(hint in name for hint in _DASHED_LINETYPE_HINTS)

    @staticmethod
    def _resolve_dash(ent: ExtractedEntity) -> tuple[list[float] | None, str | None]:
        """(dash array, unit space) for one entity.

        Prefers `linetype_pattern` -- the real LTYPE elements, resolved against the layer table
        and scaled by $LTSCALE at extraction time (`dxf_parser.resolve_dash_pattern`). Those are
        DRAWING UNITS, so the renderer applies them under the world transform and the dash
        length stays a property of the drawing rather than of the current zoom.

        Falls back to the old name-sniffing heuristic and its fixed [5, 5] for drawings ingested
        before the pattern was extracted. That fallback is in SCREEN pixels and cannot be
        anything else -- it is not derived from the drawing at all -- so the unit space travels
        with the array instead of being assumed. A stale payload keeps rendering its centre
        lines dashed rather than silently reverting them to solid.
        """
        pattern = ent.properties.get("linetype_pattern")
        if isinstance(pattern, list) and pattern:
            try:
                values = [float(v) for v in pattern]
            except (TypeError, ValueError):
                values = []
            if values and any(v > 0 for v in values):
                return values, "world"

        if GeometrySerializer._is_dashed(ent.properties.get("linetype")):
            return [5, 5], "screen"
        return None, None

    @staticmethod
    def serialize_entities(entities: list[ExtractedEntity]) -> dict[str, Any]:
        """
        Groups and normalizes geometry.
        Returns payload: { "layers": { "LAYER_NAME": [ entities ] } }
        """
        layers_map: dict[str, list[dict[str, Any]]] = {}
        layer_colors = GeometrySerializer._build_layer_colors(entities)
        layer_lineweights = GeometrySerializer._build_layer_lineweights(entities)

        for ent in entities:
            layer = ent.layer

            hex_color = GeometrySerializer._resolve_stroke(ent, layer_colors)
            stroke_width_mm = GeometrySerializer._resolve_lineweight(ent, layer_lineweights)
            dash, dash_units = GeometrySerializer._resolve_dash(ent)

            payload = {
                "id": str(ent.id),
                "handle": getattr(ent, "handle", None) or ent.properties.get("handle"),
                "type": ent.entity_type.lower(),
                "geometry": ent.geometry,
                "properties": ent.properties,
                "style": {
                    "stroke": hex_color,
                    # MILLIMETRES OF PAPER -- see `_resolve_lineweight`. The renderer must treat
                    # it as such: it used to read the number as CSS pixels and floor it at one
                    # device pixel, which collapsed this sheet's three real weights (1.00mm
                    # x136, 0.50mm x331, 0.25mm x34) into a single uniform hairline. That is why
                    # the vector linework read flat next to iCAD's.
                    "strokeWidth": stroke_width_mm,
                    "dash": dash,
                    # 'world' = drawing units (real LTYPE pattern); 'screen' = CSS pixels
                    # (legacy fallback). Absent when there is no dash.
                    "dashUnits": dash_units,
                }
            }

            # A DIMENSION's measurement text has its own colour, harvested from the rendered
            # block (see EntityMapper._dimension_render_geometry). Exposed separately from
            # `stroke` because the dimension LINES and the dimension TEXT genuinely differ --
            # green lines, yellow text is the norm on this corpus, not an anomaly.
            text_index = ent.properties.get("text_color_index")
            if text_index is not None:
                try:
                    payload["style"]["textStroke"] = GeometrySerializer._resolve_index(
                        int(text_index), layer, layer_colors
                    )
                except (TypeError, ValueError):
                    pass

            layers_map.setdefault(layer, []).append(payload)

        logger.info(
            f"Serialized {len(entities)} entities into {len(layers_map)} distinct layers "
            f"({len(layer_colors)} layer colours resolved)."
        )
        return {"layers": layers_map}
