"""
zone_ownership.py
=================
Who owns an entity when two zone boxes overlap.

Zones overlap. That is not a defect to be tuned away — it is how the sheet is laid out and how
the detector's quadrant priors are written. Measured over the corpus (12 sides), counting the
*text entities* that fall inside each intersection rather than the empty paper:

| zone pair                    | pinned | detected |
| ---------------------------- | -----: | -------: |
| `views` x `tolerance`        |     72 |     1840 |
| `views` x `title`            |     36 |      818 |
| `title` x `tolerance`        |    570 |      622 |
| `views` x `bom`              |    241 |      240 |
| `views` x `title_upper_left` |    147 |      216 |
| `bom` x `tolerance`          |      0 |       72 |
| `title_upper_left` x `tolerance` |  0 |       54 |
| `title_upper_left` x `notes` |      1 |       31 |
| `bom` x `iso`                |      1 |       24 |

**Collisions are 5-30x worse without a hand-aligned template**, which is exactly the direction
this system is trying to move in. Two of those pairs are structural, not accidental: `iso`'s
quadrant prior is `x > 0.30w` with *no y bound*, so it strictly contains `bom`'s
`x > 0.50w and y > 0.35h`; and `notes`' prior is `y > 0.15h` with *no x bound*, so it spans the
whole of `title_upper_left`'s. Those two pairs cannot be separated by the priors at all.

## Why this module exists

Before it, ownership in an intersection was decided at **four** separate call sites, with an
order that was implicit and incomplete:

  * `views_exclusions()` / `VIEWS_EXCLUDED_ZONES` -- `views` yields to everyone
  * `extract_zone_entities(exclude_bboxes=[tolerance, title, bom])` -- for `notes`
  * the same list again -- for `iso`
  * a fourth list added to `extract_title_ul_kv` on 2026-08-12 -- and **reverted the same day**
    for costing detection-only F1 0.7736 -> 0.7339

`notes` vs `iso` had **no rule in any of them**: neither pool excluded the other and the
markings are concatenated with no de-duplication, so an entity in that intersection is diffed
twice and emitted under two categories.

**That hole is latent, not live.** The census above finds `notes` x `iso` firing on **zero**
corpus sides, pinned or detected, so it has never produced a duplicate here and closing it moves
no metric. It is closed because it costs nothing to close and because the priors permit it --
not because it was hurting.

## The precedence, and why it is this order

**A zone with a drawn border outranks a zone without one.** The ruled-border spike measured, for
each zone, the best-IoU rectangle that is actually *drawn* on the sheet (chosen knowing the
answer, so it bounds any rule rather than describing one):

    views 0.97 | title 0.95 | tolerance 0.85 | title_upper_left 0.62
    bom   0.37 | notes 0.08 | iso       0.06

`title` and `tolerance` are real ruled boxes and win. `bom` and `title_upper_left` are partially
ruled and come next. `notes` and `iso` score 0.06-0.08 because **these sheets contain no drawn
box around either** — their best candidate is the whole sheet frame — so they rank last among
content zones.

`views` has the *best* border of all and still yields to everyone, because it is not a block: it
is the drawing AREA, defined by exclusion. That is a statement about what the zone means, not
about how well it can be found.

`notes` and `iso` tie, deliberately. They tie because geometry genuinely cannot rank them, which
is the same reason the notes box is unreliable in the first place. The tie is broken by content
— see `notes_classifier.py` — not by adding an arbitrary rung here.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .zone_geometry import point_in_shape, polygon_for

#: Ownership order, strongest first. Peers within a tier never evict each other.
#:
#: **Tier 0 — ruled tables.** A drawn box the detector recovers reliably, corroborated two ways:
#: the ruled-border ceiling (`title` 0.95, `tolerance` 0.85) and, decisively, the eval itself —
#: `bill_of_materials` and `title_block` score **byte-identical detected vs templated**, so
#: detection needs no human for either. `shim` joins them as a compact ruled parts table and a
#: SAFE zone whose whole job is keeping its reference rows out of everyone else's pool. `bom`'s
#: own border ceiling is only 0.37, so it sits here on the eval evidence, not the geometry.
#:
#: **Tier 1 — no reliable box.** These may not evict each other, because none of them is
#: trustworthy enough to overrule another's content.
#:
#: `title_upper_left` was ranked ABOVE `notes` first, on its 0.62 border ceiling, and that was
#: **measured wrong**. Under detection its box swallows the notes block whole — the census finds
#: 31 texts in that intersection at frac 1.00 over 6 of 12 sides — so on `M7452A0N01` it claims
#: all five notes lines and vetoing on it dropped `notes_section` recall to **0.54**. Its box
#: over-reaching *is* the defect the 2026-08-12 work was chasing; a zone cannot both be the
#: known-unreliable one and outrank a peer. The border ceiling measures how well a **hand-aligned**
#: box sits on ruled lines. It says nothing about whether the **detected** box is right, and this
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

    Pairs rather than bare boxes so a **reshaped** zone excludes only what it actually covers.
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
