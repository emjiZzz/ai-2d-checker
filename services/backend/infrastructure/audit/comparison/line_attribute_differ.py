"""Line attributes -- the line types and thicknesses a drawing view is actually drawn with.

Exists because `line_attributes` was a checklist sub-item with no producer, so it reported "No
changes detected." on every comparison this system had ever run.

Deterministic, because nothing here infers: the drawing states these attributes and this reads
them back from `common_properties`, resolving BYLAYER against the `layer` records.

Two rules, both measured rather than chosen. The key is `(linetype, lineweight)` and colour is
deliberately not an axis -- adding it roughly doubles the rows, and on this corpus colour is a
house convention on top of the line type rather than a line attribute, so the section cut plane
and the part centreline differ only by ACI index. And presence decides the status while a stroke
count never does: the revision is a re-trace rather than a copy, so counts differ on almost every
sheet and a count-driven CHANGED would fire on nearly every comparison and mean nothing.

The measurements behind both, and the reverted `geometry_differ` that established the second, are
in `06 - .../Gotcha - A Checklist Item With No Producer Reported Clean.md`. See also
`06 - .../Gotcha - The Differ Compared Text Only.md`.
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


def describe(key: tuple[str, float]) -> str:
    """The ORIGINAL/REVISION cell for one profile row: `CENTER 0.25mm`.

    No stroke count. This card answers "what kind of line types does the drawing use",
    which is a question about the SET of line types, not about how many strokes each one
    drew. The count used to be part of this string, and that was wrong in three ways at once
    (owner's report, 2026-08-17):

    1. It made the count the card's headline — `CENTER 0.25MM X9` — while `status` explicitly
       ignores counts, so the card read as self-contradictory: `x20` against `x2`, MATCHED.
    2. It put the count in the row's IDENTITY, so the same line type rendered as a different
       card whenever a re-trace moved the tally. A revision is a re-trace, so it moves nearly
       every time.
    3. `text_content` is what `markerGenerator.ts` fuzzy-matches against sheet text, so the
       count was also feeding the phantom-marker path.

    The count is still computed (`profile_line_attributes`) and is available to anything that
    wants it; it is simply not something this card claims.
    """
    linetype, weight_mm = key
    return f"{linetype} {weight_mm:g}mm"


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

        # The row IS the line type. Stroke counts are deliberately absent from every
        # user-facing string — see `describe`.
        label = describe(key)

        if ref_bucket and rev_bucket:
            status = "MATCHED"
            text_content = label
            original_value = label
            details = (
                f"Both drawings use {linetype} at {weight_mm:g}mm in the drawing views."
            )
        elif rev_bucket:
            status = "ADDED"
            text_content = label
            original_value = None
            details = (
                f"The revision uses {linetype} at {weight_mm:g}mm in the drawing views. "
                f"The reference uses this line type nowhere."
            )
        else:
            status = "REMOVED"
            text_content = label
            original_value = label
            details = (
                f"The reference uses {linetype} at {weight_mm:g}mm in the drawing views. "
                f"The revision uses this line type nowhere."
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
