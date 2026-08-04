"""Where a checklist marker's glyph is drawn, in CAD units.

`renderEntities.ts` draws the marker glyph with `textAlign='center'` and
`textBaseline='middle'` at exactly the coordinate it is given, so **the coordinate IS the
glyph's centre**. Every anchor in this codebase must therefore be the centre of the thing the
marker refers to.

They previously were not. The formula was `[bbox.xmax + height * 0.8, vertical centre]` --
the glyph sat one character-width PAST the end of the text. On a short value that reads as a
tick beside the data; on a long one (`M7452A1N01`, a wrapped title row) it pushes the glyph
clear of the value and, in the title block, outside the ruled cell the value lives in, so the
tick appears to annotate whatever happens to sit to the right.

That formula was hand-copied to twelve places in Python and eight in TypeScript, all of which
had to agree. This module is the single Python definition; the TypeScript mirror is
`markerAnchor()` in `apps/desktop/src/utils/markerGenerator.ts`.

Trade-off, accepted deliberately: a centred glyph overlaps the text it marks. That is what
makes the association unambiguous, which is the point -- a trailing glyph is ambiguous
precisely when values are packed tightly, which in a title block is always.
"""
from typing import Any, Optional

# Fraction of the text height used as the per-character advance when a real bbox is missing.
# Only reached for entities whose extraction produced no bbox; the estimate just needs to put
# the anchor inside the text, not to be typographically exact.
_CHAR_WIDTH_RATIO = 0.6

# DXF justification codes that mean the insert point is already the horizontal centre.
_CENTERED_HALIGN = (1, 4)
_CENTERED_ATTACHMENT = (2, 5, 8)


def marker_anchor(
    bbox: Optional[Any] = None,
    insert: Optional[Any] = None,
    height: float = 3.0,
    text: str = "",
    is_centered: bool = False,
) -> Optional[list]:
    """Centre of a piece of drawing text. Prefers the real bbox; estimates from insert if not.

    `is_centered` says the insert point is already the horizontal centre (centred/middle-
    justified text, and dimensions). Left-justified text has its insert at the left edge, so
    half the estimated width is added.
    """
    if bbox is not None:
        try:
            (xmin, ymin), (xmax, ymax) = bbox[0][:2], bbox[1][:2]
            return [(float(xmin) + float(xmax)) / 2.0, (float(ymin) + float(ymax)) / 2.0]
        except (TypeError, IndexError, ValueError):
            pass

    if not insert:
        return None
    try:
        ix, iy = float(insert[0]), float(insert[1])
    except (TypeError, IndexError, ValueError):
        return None

    h = float(height or 3.0)
    width = len(text or "") * h * _CHAR_WIDTH_RATIO
    cx = ix if is_centered else ix + (width / 2.0)
    # The insert sits on the text baseline, so the vertical centre is half a height above it.
    return [cx, iy + (h / 2.0)]


def entity_is_centered(entity: Any) -> bool:
    """Whether `entity`'s insert point is already its horizontal centre."""
    props = getattr(entity, "properties", None) or {}
    if getattr(entity, "entity_type", "") == "dimension":
        return True
    return (
        props.get("halign", 0) in _CENTERED_HALIGN
        or props.get("attachment_point", 0) in _CENTERED_ATTACHMENT
    )
