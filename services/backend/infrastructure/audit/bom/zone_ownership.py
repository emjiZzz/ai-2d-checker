"""Who owns an entity when two zone boxes overlap.

Zones overlap by design, and one arbitration answers this rather than the four ad-hoc exclusion
lists that used to. The order: a zone with a drawn border outranks one without, so `title` and
`tolerance` win, `bom` and `title_upper_left` follow, and `notes` and `iso` rank last because
these sheets draw no box around either. `views` has the best border of all and still yields to
everyone, because it is not a block -- it is the drawing area, defined by exclusion. `notes` and
`iso` tie deliberately, and the tie is broken by content in `notes_classifier.py` rather than by
an arbitrary rung here.

The overlap census, the ruled-border IoU numbers behind that ranking, and the four call sites this
replaced are in
`docs/vault/02 - Audit Comparison Engines/Zone Detector & Bounding Boxes.md`, under "Zone
ownership when boxes overlap". Read it before reordering anything: two of the pairs overlap
structurally, because the quadrant priors make it unavoidable, so the order is not tunable.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .zone_geometry import point_in_shape, polygon_for

#: Ownership order, strongest first. Peers within a tier never evict each other.
#:
#: Tier 0 — ruled tables. A drawn box the detector recovers reliably, corroborated two ways:
#: the ruled-border ceiling (`title` 0.95, `tolerance` 0.85) and, decisively, the eval itself —
#: `bill_of_materials` and `title_block` score byte-identical detected vs templated, so
#: detection needs no human for either. `shim` joins them as a compact ruled parts table and a
#: SAFE zone whose whole job is keeping its reference rows out of everyone else's pool. `bom`'s
#: own border ceiling is only 0.37, so it sits here on the eval evidence, not the geometry.
#:
#: Tier 1 — no reliable box. These may not evict each other, because none of them is
#: trustworthy enough to overrule another's content.
#:
#: `title_upper_left` was ranked ABOVE `notes` first, on its 0.62 border ceiling, and that was
#: measured wrong. Under detection its box swallows the notes block whole — the census finds
#: 31 texts in that intersection at frac 1.00 over 6 of 12 sides — so on `M7452A0N01` it claims
#: all five notes lines and vetoing on it dropped `notes_section` recall to 0.54. Its box
#: over-reaching *is* the defect the 2026-08-12 work was chasing; a zone cannot both be the
#: known-unreliable one and outrank a peer. The border ceiling measures how well a hand-aligned
#: box sits on ruled lines. It says nothing about whether the detected box is right, and this
#: is the pair where those two diverge. Peers now, with content breaking the tie: the UL table's
#: values are short codes and note lines are instruction sentences, which no box needs to separate.
ZONE_PRECEDENCE: tuple[tuple[str, ...], ...] = (
    ("title", "tolerance", "bom", "shim"),
    ("title_upper_left", "notes", "iso"),
    ("views",),
)

#: Flattened, strongest first. Zones absent from here are unknown to the arbitration and are
#: never claimed as an owner — a reserved `regions` key like `_zone_polygons` must not become a
#: zone by accident.
ZONE_ORDER: tuple[str, ...] = tuple(z for tier in ZONE_PRECEDENCE for z in tier)

#: Rank per zone; lower wins.
_RANK: dict[str, int] = {
    zone: i for i, tier in enumerate(ZONE_PRECEDENCE) for zone in tier
}


def rank_of(zone: str) -> Optional[int]:
    """Precedence tier of `zone`, or None when it is not an arbitrated zone."""
    return _RANK.get(zone)


def shapes_for(regions: Optional[dict], zones: Iterable[str]) -> list[tuple]:
    """`(bbox, outline)` pairs for `zones` present in `regions`, in precedence order.

    Pairs rather than bare boxes so a reshaped zone excludes only what it actually covers.
    Using its bounding box instead over-excludes: content sitting in a notch the user cut out of
    a zone would be dropped from the other pool as well and land in no category at all. That is
    the silent false-negative direction, which is the one this system cannot detect.
    """
    wanted = set(zones)
    return [
        (bbox, polygon_for(regions, key))
        for key in ZONE_ORDER
        if key in wanted and (bbox := (regions or {}).get(key))
    ]


def exclusions_for(zone: str, regions: Optional[dict]) -> list[tuple]:
    """Shapes that outrank `zone` and must be subtracted from its pool.

    Replaces the per-call-site `exclude_bboxes` lists. A zone never excludes itself, and never
    excludes a peer in its own tier — peers tie, and a tie is not resolved by whichever pool
    happens to be built first.
    """
    mine = rank_of(zone)
    if mine is None:
        return []
    return shapes_for(regions, [z for z in ZONE_ORDER if (_RANK[z] < mine)])


def owner_of(
    x: float,
    y: float,
    regions: Optional[dict],
    *,
    candidates: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """The zone that owns point (x, y), or None when no arbitrated zone covers it.

    Walks in precedence order and returns the first zone whose *shape* contains the point, so an
    entity in an intersection is claimed exactly once. `candidates` narrows the search when a
    caller only cares about a subset.
    """
    allowed = set(candidates) if candidates is not None else None
    for key in ZONE_ORDER:
        if allowed is not None and key not in allowed:
            continue
        bbox = (regions or {}).get(key)
        if bbox and point_in_shape(x, y, bbox, polygon_for(regions, key)):
            return key
    return None


def is_owned_by_other(
    x: float,
    y: float,
    regions: Optional[dict],
    zone: str,
) -> bool:
    """True when a zone that outranks `zone` covers this point.

    The question `extract_zone_entities` is really asking, phrased so the caller does not have to
    know the order. Peers do not evict: `notes` and `iso` tie, so neither takes the other's
    content here and the tie falls to the content classifier.
    """
    mine = rank_of(zone)
    if mine is None:
        return False
    owner = owner_of(x, y, regions)
    return owner is not None and _RANK[owner] < mine
