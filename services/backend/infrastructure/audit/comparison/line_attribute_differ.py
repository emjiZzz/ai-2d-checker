"""Line attributes — the line types and thicknesses a drawing view is actually drawn with.

`line_attributes` has been a `drawing_views` sub-item since the checklist was grouped, and
nothing has ever produced a finding for it. `feature_classifier` says so in its own module
docstring: `origin`, `alignment_of_views`, `line_attributes` and `text_attributes` "have no
reliable text-level signal at all and are never assigned by these rules", with Generator B —
the one that reasoned visually over the rendered image — named as the intended source.
ADR-006 removed Generator B. The card was therefore reachable only through its empty state,
and that empty state reads **"No changes detected."**

A check that never ran, reporting clean, is the one failure mode this system says it cannot
detect. `line_name` is handled honestly for exactly this reason — it sits in
`taxonomy.DEFERRED_FEATURES` and the frontend renders it "Not yet supported for automatic
checking". `line_attributes` never got that treatment, so it has been claiming a clean result
for every comparison this system has ever run.

## Why this one can be deterministic

Nothing here infers, guesses or thresholds. The drawing states its line attributes and this
reads them back: `entity_mapper.common_properties` writes `linetype`, `lineweight`, `color`
and `ltscale` onto every graphic entity, and `dxf_parser` records the same attributes on each
`layer` record so a BYLAYER entity can be resolved against its layer.

Measured across the 42 drawings in `storage/uploads`, the whole corpus draws with **four**
line types: CONTINUOUS (16200 strokes), CENTER (818), DASHED (684) and HIDDEN (2).

## The key is (linetype, lineweight). Colour is not an axis — measured, not assumed.

Distinct profile rows per sheet, over the same 42 drawings:

| key                            | min | median | max |
| :----------------------------- | --: | -----: | --: |
| (linetype, lineweight)         |   4 |      5 |   7 |
| (linetype, lineweight, colour) |   8 |     11 |  15 |

Five rows is a checklist card; eleven is a wall, and the reverted `geometry_differ` is on
record for drowning the panel. Colour is also the wrong axis for this item on this corpus: it
is a house convention layered *on top of* the line type, not a line attribute in its own
right. The section cut plane and the part centreline are both CENTER at 0.25mm and differ
only by ACI index — `sectionCallouts.ts` identifies the cut plane by exactly that, and
documents it as a client convention rather than something the DXF states. "Line attributes"
in drafting review means 線種 and 線の太さ. Colour is carried in `details` for context and
never splits a row.

## Presence decides the status. A count difference never does.

`geometry_differ` was built and reverted for emitting findings like `Geometry: 10 line` —
"a count and a primitive type and nothing else", which a checker cannot act on. Its lesson is
recorded as: **a finding must say what changed, not how many primitives differ.**

So a row is MATCHED when both sides draw with that (linetype, lineweight), ADDED when only
the revision does, and REMOVED when only the reference does. Stroke counts are reported in
the ORIGINAL/REVISION cells and in `details`, and are never promoted to a status.

That matters on real pairs specifically. The revision is a re-trace rather than a copy, so
stroke counts differ on almost every sheet — the pair in the reported case draws the same
feature as two arcs on one side and two full circles on the other. A count-driven CHANGED
would fire on nearly every comparison and mean nothing, which is precisely how the reverted
implementation trained a checker to skim past the panel. Presence is the half that carries
engineering meaning: a HIDDEN line type that exists on one side and not the other is a real
finding, and on this corpus HIDDEN appears exactly twice.

See `docs/vault/06 - Gotchas & Debugging Lessons/Gotcha - The Differ Compared Text Only.md`.
"""

from collections import Counter
from typing import Any

from ...cad.dxf_parser import SOLID_LINETYPE_NAMES
from ...rendering.geometry_serializer import (
    ACI_BYLAYER,
    LINEWEIGHT_BYLAYER,
    GeometrySerializer,
)

#: Entity types whose stroke carries a line attribute worth checking.
#:
#: `dimension`, `leader` and `multileader` are excluded for the same reason
#: `COMPARABLE_ENTITY_TYPES` excludes them from the text pools: their meaning is their
#: annotation, and their stroke is drawn by a dimension style rather than chosen by the
#: drafter. `hatch` is excluded because a fill's attributes restate its boundary's.
STROKE_ENTITY_TYPES: frozenset[str] = frozenset(
    {"line", "circle", "arc", "polyline", "ellipse", "spline"}
)

#: What `linetype` resolves to when the name means "no pattern". Collapsing the aliases here
#: keeps CONTINUOUS from splitting into three rows that say the same thing.
CONTINUOUS = "CONTINUOUS"

#: The taxonomy sub-item these findings file under. `drawing_views` is the category.
FEATURE_KEY = "line_attributes"


def build_layer_linetypes(entities: list) -> dict[str, str]:
    """Layer name -> linetype name, from the `layer` records in the same entity set.

    Kept separate from the stroke pool on purpose: a `layer` record has no geometry, so
    `zone_detector.entity_anchor` returns None for it and `scope_entities_to_views` drops it.
    The layer table has to be built from the drawing's FULL entity list even when the profile
    is being counted over a zone-scoped subset, or every BYLAYER stroke resolves against an
    empty table and lands in CONTINUOUS.
    """
    table: dict[str, str] = {}
    for ent in entities:
        if str(getattr(ent, "entity_type", "") or "").lower() != "layer":
            continue
        raw = (getattr(ent, "properties", {}) or {}).get("linetype", CONTINUOUS)
        table[getattr(ent, "layer", "")] = str(raw or CONTINUOUS)
    return table


def resolve_linetype(entity: Any, layer_linetypes: dict[str, str]) -> str:
    """The line type this entity is actually drawn with, uppercased.

    BYLAYER resolves through the layer table exactly as `dxf_parser.resolve_dash_pattern`
    does, and BYBLOCK collapses to CONTINUOUS for the same reason it does there — it is in
    `SOLID_LINETYPE_NAMES`. That is a known simplification: the colour path walks the INSERT
    chain for BYBLOCK (`GeometrySerializer._inherited_from_insert`) and the linetype path does
    not. It is left alone deliberately, because the checklist must describe the same strokes
    the canvas paints, and resolving BYBLOCK here while the renderer treats it as solid would
    make the two disagree. It is also nearly unreachable: 3 entities in the whole corpus carry
    a BYBLOCK linetype.
    """
    name = str((getattr(entity, "properties", {}) or {}).get("linetype", "") or "").upper()
    if name in ("BYLAYER", ""):
        name = str(layer_linetypes.get(getattr(entity, "layer", ""), "") or "").upper()
    return CONTINUOUS if name in SOLID_LINETYPE_NAMES else name


def resolve_lineweight_mm(entity: Any, layer_lineweights: dict[str, int]) -> float:
    """Stroke width in millimetres, delegating to the renderer's own resolution.

    `GeometrySerializer._resolve_lineweight` already handles the three sentinels (BYLAYER,
    BYBLOCK, DEFAULT -> $LWDEFAULT) and is what the canvas draws with. Reimplementing that
    arithmetic here would give the checklist a second opinion about how thick a line is, and
    two implementations of one rule that disagree are worse than one rule reached across a
    module boundary.
    """
    return GeometrySerializer._resolve_lineweight(entity, layer_lineweights)


def _dominant_colour(indices: Counter) -> int | None:
    """The ACI index most of a bucket's strokes carry, for `details` only — never a row key."""
    if not indices:
        return None
    return indices.most_common(1)[0][0]


def profile_line_attributes(
    stroke_entities: list,
    layer_linetypes: dict[str, str],
    layer_lineweights: dict[str, int],
) -> dict[tuple[str, float], dict[str, Any]]:
    """(linetype, lineweight_mm) -> {count, colours} over one side's stroke geometry."""
    profile: dict[tuple[str, float], dict[str, Any]] = {}
    for ent in stroke_entities:
        if str(getattr(ent, "entity_type", "") or "").lower() not in STROKE_ENTITY_TYPES:
            continue
        key = (
            resolve_linetype(ent, layer_linetypes),
            resolve_lineweight_mm(ent, layer_lineweights),
        )
        bucket = profile.setdefault(key, {"count": 0, "colours": Counter()})
        bucket["count"] += 1
        try:
            aci = int((getattr(ent, "properties", {}) or {}).get("color", ACI_BYLAYER))
        except (TypeError, ValueError):
            aci = ACI_BYLAYER
        bucket["colours"][aci] += 1
    return profile


def describe(key: tuple[str, float], count: int) -> str:
    """The ORIGINAL/REVISION cell for one profile row: `CENTER 0.25mm x12`.

    ASCII `x`, not `×`. Every string on this path is re-encoded latin-1 by `transcode_value`
    and passed through `safe_decode`'s mojibake repair, which is on record for corrupting a
    literal `±` into halfwidth katakana. A multiplication sign buys nothing worth testing that
    pipeline for.
    """
    linetype, weight_mm = key
    return f"{linetype} {weight_mm:g}mm x{count}"


def diff_line_attributes(
    ref_stroke_entities: list,
    rev_stroke_entities: list,
    ref_all_entities: list,
    rev_all_entities: list,
    category: str = "drawing_views",
) -> list[dict]:
    """One marking per (linetype, lineweight) either side of the comparison draws with.

    `ref_stroke_entities`/`rev_stroke_entities` are the zone-scoped pools — the strokes inside
    the `views` box. `ref_all_entities`/`rev_all_entities` are the drawings' full entity lists,
    read ONLY for their `layer` records; see `build_layer_linetypes`.

    Markings carry no `coordinates`. A profile row describes every stroke of one kind across
    the whole view, so there is no single point a canvas marker could honestly sit at, and
    `inject_title_block_markings` already establishes coordinate-free markings as a supported
    shape. The consequence is deliberate: these rows fill the checklist card without adding
    pins to the drawing.
    """
    ref_profile = profile_line_attributes(
        ref_stroke_entities,
        build_layer_linetypes(ref_all_entities),
        GeometrySerializer._build_layer_lineweights(ref_all_entities),
    )
    rev_profile = profile_line_attributes(
        rev_stroke_entities,
        build_layer_linetypes(rev_all_entities),
        GeometrySerializer._build_layer_lineweights(rev_all_entities),
    )

    markings: list[dict] = []
    # Heaviest line first, then by name: on a mechanical drawing the outline is the thing the
    # checker looks at first, and a stable order stops the card reshuffling between runs.
    for key in sorted(set(ref_profile) | set(rev_profile), key=lambda k: (-k[1], k[0])):
        ref_bucket = ref_profile.get(key)
        rev_bucket = rev_profile.get(key)
        linetype, weight_mm = key

        if ref_bucket and rev_bucket:
            status = "MATCHED"
            text_content = describe(key, rev_bucket["count"])
            original_value = describe(key, ref_bucket["count"])
            details = (
                f"Line attribute {linetype} at {weight_mm:g}mm is used on both drawings "
                f"({ref_bucket['count']} strokes on the reference, {rev_bucket['count']} on "
                f"the revision). Stroke counts differ on any re-traced drawing and are not "
                f"treated as a change."
            )
        elif rev_bucket:
            status = "ADDED"
            text_content = describe(key, rev_bucket["count"])
            original_value = None
            details = (
                f"The revision draws {rev_bucket['count']} stroke(s) with {linetype} at "
                f"{weight_mm:g}mm. The reference uses this line attribute nowhere in the "
                f"drawing views."
            )
        else:
            status = "REMOVED"
            text_content = describe(key, ref_bucket["count"])
            original_value = text_content
            details = (
                f"The reference draws {ref_bucket['count']} stroke(s) with {linetype} at "
                f"{weight_mm:g}mm. The revision uses this line attribute nowhere in the "
                f"drawing views."
            )

        colours = Counter()
        for bucket in (ref_bucket, rev_bucket):
            if bucket:
                colours.update(bucket["colours"])
        aci = _dominant_colour(colours)
        if aci is not None and aci != ACI_BYLAYER:
            details += f" Predominant colour index {aci}."

        markings.append(
            {
                "text_content": text_content,
                "status": status,
                "details": details,
                "category": category,
                "feature": FEATURE_KEY,
                "original_value": original_value,
            }
        )

    return markings


__all__ = [
    "CONTINUOUS",
    "FEATURE_KEY",
    "LINEWEIGHT_BYLAYER",
    "STROKE_ENTITY_TYPES",
    "build_layer_linetypes",
    "describe",
    "diff_line_attributes",
    "profile_line_attributes",
    "resolve_linetype",
    "resolve_lineweight_mm",
]
