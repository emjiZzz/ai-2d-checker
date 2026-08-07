"""Synthetic drawing pairs whose ground truth is known by construction — Stage 0c.

A mutation pair is a base drawing and a deliberately edited copy of it. The generator knows
exactly what it edited, so the labels write themselves: no annotator, no judgement calls,
and as many pairs as you want. That is what makes a precision/recall number reachable
before the human corpus exists, and it is the free training supervision Stage 3's learned
matcher depends on.

## The zero-finding operators are the point

Three of the eight operators are designed to produce **no** finding:

  * `null_mutation` — re-save with no edit at all. Ground truth is zero findings, so every
    finding produced is a measured false positive. Highest-value operator here.
  * `restyle_dimension_text` — rewrite a dimension's display override (`%%c120` → `120`)
    without touching its `measurement`. Per the annotation guideline that is a transcoding,
    not a change. Aimed squarely at the bug class of
    [[Gotcha - The Differ Compared Text Only]].
  * `translate_entities` — move text a short distance without editing it. The guideline:
    pure relocation with identical text is not a finding.

An engine can score well on the editing operators while failing all three of these, and the
failure would be invisible without them.

## What a mutation pair does *not* measure

**Category attribution is not independent here.** An operator picks its target *inside* a
detected zone and derives the finding's category from that zone, so the label agrees with
`zone_detector` by construction. A mutation pair therefore measures detection honestly and
category attribution circularly. Only human pairs can gate a category-attribution claim —
the same restriction the plan already places on Stage 3's learned matcher, for the same
reason.

## Why the mutated side gets its own drawing id

`extract_title_block` lets a cached OCR value **win** over the spatial reading
(`title_block_extractor.py:490-509`). If both sides shared one OCR cache entry, a title
mutation would be masked and its label would be a guaranteed false negative caused by the
harness rather than by the engine. So each mutated side gets a synthetic, seed-derived
`drawing_id` and the generator writes it a **derived** OCR cache entry: a copy of the base's,
with the same edit applied. Offline-ness is preserved and `title_block` stays measurable.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .corpus import ExpectedFinding
from .serialize import EvalDrawing, EvalEntity

# Bump when an operator's semantics change such that previously generated pairs no longer
# mean what their labels say. Recorded per pair so a stale pair is identifiable.
#
# v2: zone scoping honours the sheet's hand-aligned template (see `Mutator.__init__`). Both
#     halves of a v1 label are affected, not just one: the regions decide **where** a
#     mutation may land and **which category** its finding gets, so a v1 pair was targeted
#     and categorised against detector boxes while the engine now compares against pinned
#     ones. v1 pairs must be regenerated, not re-scored.
MUTATION_SCHEMA_VERSION = 2

# Zones an operator may target, and the category a finding inside each implies.
ZONE_CATEGORY: dict[str, str] = {
    "views": "drawing_views",
    "notes": "notes_section",
    "bom": "bill_of_materials",
    "title": "title_block",
    "iso": "isometric_view",
}

# Never mutate inside these. `tolerance` and the shim table are reference data the engine
# deliberately never compares, so an edit there has ground truth "no finding" — which is a
# legitimate probe, but a *different* one from the operators here, and mixing it in would
# silently inflate their false-positive counts.
SAFE_ZONES = frozenset({"tolerance", "shim"})

# Title fields whose value the OCR cache carries, keyed by the cache's own field names.
# A title mutation must edit both the entity and this, or the OCR value wins and hides it.
OCR_FIELDS = ("TITLE", "DWG_NO", "DRAWN", "DESIGNED", "SCALE", "QTY")

_DIGITS = re.compile(r"\d+")


@dataclass
class MutationPair:
    """One generated pair: the mutated entities, and the findings they imply."""

    pair_id: str
    base_pair_id: str
    seed: int
    drawing: EvalDrawing
    entities: list[EvalEntity]
    findings: list[ExpectedFinding]
    applied: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    ocr_override: dict[str, Any] | None = None

    @property
    def is_null_pair(self) -> bool:
        """True when ground truth is zero findings — the pure precision probe."""
        return not self.findings

    def summary(self) -> str:
        ops = ", ".join(self.applied) or "none"
        return f"{self.pair_id}: {len(self.findings)} finding(s) from [{ops}]"


@dataclass
class _Pending:
    """A finding recorded before its address can be computed.

    Addresses cannot be resolved during mutation: a deletion shifts every later index, so
    a revision-side address is only meaningful once the final entity list exists. Reference
    -side addresses are stable throughout — that list is never mutated.
    """

    side: str
    category: str
    status: str
    ref_text: str
    rev_text: str
    notes: str
    entity: EvalEntity | None = None  # revision side: resolved by identity at the end
    ref_index: int = -1  # reference side: index into the untouched base list


class Mutator:
    """Generates mutation pairs from one base drawing.

    Deterministic given a seed: the same seed produces byte-identical entities and an
    identical finding list, which is what lets a sweep re-run a pair and compare.
    """

    def __init__(
        self,
        base_drawing: EvalDrawing,
        base_entities: list[EvalEntity],
        base_ocr: dict[str, Any] | None = None,
        zone_template: dict[str, Any] | None = None,
    ) -> None:
        from ..audit.bom.table_extractor import extract_dynamic_regions_with_template
        from ..audit.bom.zone_detector import entity_anchor

        self.base_drawing = base_drawing
        self.base_entities = base_entities
        self.base_ocr = base_ocr or {}
        self._anchor = entity_anchor

        # These regions do two jobs: they decide **where a mutation may land** and they
        # assign each ExpectedFinding its **category**. So they have to be the boxes the
        # engine will use, or the corpus grades the engine against an answer key describing
        # a different sheet layout.
        #
        # This used to call the detection-only `extract_dynamic_regions`. When the eval
        # started applying hand-aligned templates offline, the engine moved and the labels
        # did not: attribution fell 0.81 -> 0.74 and a `notes_section -> drawing_views`
        # confusion appeared out of nothing, entirely because the template's notes box is
        # tighter than the detector's. The engine was right seven times and the label was
        # stale. See docs/vault/06 - .../Gotcha - Mutation Labels Predate the Zone Template.
        #
        # `zone_template=None` keeps the old detection-only behaviour, which is correct for
        # a sheet whose layout nobody has pinned.
        self.zone_template = zone_template
        self.regions = extract_dynamic_regions_with_template(
            base_entities,
            render_bounds=(base_drawing.metadata or {}).get("render_bounds"),
            zone_template=zone_template,
        )
        self.zones: dict[str, tuple] = {
            key: tuple(value)
            for key, value in self.regions.items()
            if key in ZONE_CATEGORY and isinstance(value, (list, tuple)) and len(value) == 4
        }
        self.safe_boxes: list[tuple] = [
            tuple(self.regions[key])
            for key in SAFE_ZONES
            if isinstance(self.regions.get(key), (list, tuple)) and len(self.regions[key]) == 4
        ]
        self.bom_values = _bom_cell_values(base_entities, self.regions)

    # -- targeting ---------------------------------------------------------
    #
    # A mutation must land on something the engine actually compares, or its label is
    # unsatisfiable: the first run of this generator dutifully deleted a BOM column header
    # and a margin grid label and then recorded them as missed findings. Neither is a
    # finding under the annotation guideline — grid labels and table furniture are on its
    # "what is not a finding" list — so the recall miss was the mutator's, not the engine's.
    #
    # **Limitation, stated rather than buried:** targeting the engine's own comparison pool
    # means a mutation can never land somewhere the pool wrongly excludes. Mutation pairs
    # therefore cannot detect a *scoping* bug — and scoping bugs are a real class here; see
    # [[Gotcha - Dimension Scoped by Its Span Midpoint]], where an over-grown safe zone
    # silently dropped four entities from comparison. Only human pairs can catch that.

    def _in_box(self, entity: EvalEntity, box: tuple) -> bool:
        point = self._anchor(entity)
        if not point or len(point) < 2:
            return False
        return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]

    def _in_safe_zone(self, entity: EvalEntity) -> bool:
        return any(self._in_box(entity, box) for box in self.safe_boxes)

    def _views_pool(self, entities: list[EvalEntity]) -> list[EvalEntity]:
        """The `drawing_views` comparison pool, built the way the orchestrator builds it."""
        from ..audit.bom.zone_detector import scope_entities_to_views, views_exclusions

        return scope_entities_to_views(
            entities, self.regions.get("views"), views_exclusions(self.regions)
        )

    def _is_excluded(self, entity: EvalEntity) -> bool:
        from ..audit.bom.spatial_utils import compute_drawing_bounds
        from ..audit.bom.zone_detector import is_margin_grid_text

        if self._bounds is None:
            self._bounds = compute_drawing_bounds(self.base_entities)
        return bool(is_margin_grid_text(entity, self._bounds)) or self._in_safe_zone(entity)

    _bounds: tuple | None = None

    def candidates(
        self, entities: list[EvalEntity], zone: str, entity_type: str = "text"
    ) -> list[EvalEntity]:
        """Mutable targets in one zone that the engine would actually compare.

        `views` goes through the orchestrator's own scoping so a mutation cannot land
        outside the views box. `bom` is restricted to text matching a cell the row
        extractor actually produced — editing a column header is not a BOM row change and
        labelling it as one manufactures a recall miss.
        """
        from ..audit.comparison.spatial_differ import COMPARABLE_ENTITY_TYPES

        if entity_type not in COMPARABLE_ENTITY_TYPES:
            return []

        if zone == "views":
            pool = [e for e in self._views_pool(entities) if e.entity_type == entity_type]
        else:
            box = self.zones.get(zone)
            if not box:
                return []
            pool = [e for e in entities if e.entity_type == entity_type and self._in_box(e, box)]

        pool = [
            e
            for e in pool
            if str(e.properties.get("text") or "").strip() and not self._is_excluded(e)
        ]
        if zone == "bom":
            pool = [e for e in pool if _text_of(e).strip() in self.bom_values]
        return pool

    # -- generation --------------------------------------------------------

    def generate(
        self,
        pair_id: str,
        *,
        seed: int,
        operators: list[str] | None = None,
        edits: int = 3,
    ) -> MutationPair:
        rng = random.Random(seed)
        entities = deepcopy(self.base_entities)
        pending: list[_Pending] = []
        applied: list[str] = []
        rejected: list[str] = []
        ocr_override = dict(self.base_ocr) if self.base_ocr else None

        chosen = list(operators) if operators else self._pick_operators(rng, edits)
        for name in chosen:
            operator = OPERATORS.get(name)
            if operator is None:
                rejected.append(f"{name} (unknown operator)")
                continue
            outcome = operator(self, rng, entities, pending, ocr_override)
            if outcome is None:
                # No eligible target on this drawing. Recorded, not silently skipped: a
                # generator that quietly produces fewer edits than requested makes an
                # aggregate look better than the corpus it was measured on.
                rejected.append(f"{name} (no eligible target)")
            else:
                applied.append(name)

        drawing = self._mutated_drawing(pair_id, seed)
        findings = self._resolve(pending, entities)
        return MutationPair(
            pair_id=pair_id,
            base_pair_id=self.base_drawing.file_name,
            seed=seed,
            drawing=drawing,
            entities=entities,
            findings=findings,
            applied=applied,
            rejected=rejected,
            ocr_override=ocr_override,
        )

    def _pick_operators(self, rng: random.Random, edits: int) -> list[str]:
        """A weighted draw, with the zero-finding probes always in the pool.

        `null_mutation` is drawn as a whole pair rather than as one edit among several —
        its ground truth is "zero findings", which only means anything if nothing else
        ran.
        """
        if rng.random() < 0.2:
            return ["null_mutation"]
        pool = [name for name, spec in OPERATOR_WEIGHTS.items() if spec > 0]
        weights = [OPERATOR_WEIGHTS[name] for name in pool]
        picked: list[str] = []
        for _ in range(max(1, edits)):
            picked.append(rng.choices(pool, weights=weights, k=1)[0])
        return picked

    def _mutated_drawing(self, pair_id: str, seed: int) -> EvalDrawing:
        """A distinct identity for the mutated side, derived from the pair id and seed.

        Distinct because it must resolve to its *own* title-block OCR cache entry — see
        the module docstring. Derived, so re-running the same seed reuses the same entry
        instead of littering the cache.
        """
        token = hashlib.sha256(f"{self.base_drawing.id}:{pair_id}:{seed}".encode()).hexdigest()
        drawing = deepcopy(self.base_drawing)
        drawing.id = f"mut{token[:21]}"
        drawing.file_hash = token
        drawing.file_name = f"{pair_id}.dxf"
        return drawing

    def _resolve(
        self, pending: list[_Pending], entities: list[EvalEntity]
    ) -> list[ExpectedFinding]:
        """Turn pending records into addressed findings, now that indices are final."""
        position = {id(entity): index for index, entity in enumerate(entities)}
        findings: list[ExpectedFinding] = []
        for item in pending:
            if item.side == "REF":
                base = self.base_entities[item.ref_index]
                address = f"REF-{base.handle}" if base.handle else f"REF#{item.ref_index}"
            else:
                entity = item.entity
                if entity is None:
                    continue
                index = position.get(id(entity))
                if index is None:
                    # The operator edited an entity that a later operator deleted. The
                    # finding is unaddressable, so it is dropped rather than pointed at
                    # nothing — an unresolvable label reads as a corpus defect downstream.
                    continue
                address = f"REV-{entity.handle}" if entity.handle else f"REV#{index}"
            findings.append(
                ExpectedFinding(
                    entity_handle=address,
                    category=item.category,
                    status=item.status,
                    ref_text=item.ref_text,
                    rev_text=item.rev_text,
                    notes=item.notes,
                )
            )
        return findings


# ── operators ─────────────────────────────────────────────────────────────────────────
#
# Each takes (mutator, rng, entities, pending, ocr) and returns a short description, or
# None when the drawing offers no eligible target. Mutating `entities` and appending to
# `pending` is how they report; addresses are resolved afterwards.

Operator = Callable[
    ["Mutator", random.Random, list[EvalEntity], list[_Pending], "dict[str, Any] | None"],
    "str | None",
]


def _text_of(entity: EvalEntity) -> str:
    return str(entity.properties.get("text") or "")


def _bom_cell_values(entities: list[EvalEntity], regions: dict[str, Any]) -> set[str]:
    """Cell values the BOM row extractor actually produced.

    A BOM finding comes from row extraction, not from the spatial differ, so mutating a
    column header or a stray label inside the BOM box changes nothing the engine reports.
    Restricting targets to real cell values is what makes a `bill_of_materials` label
    satisfiable.
    """
    try:
        # `extract_bom_table`, not `row_extractor.extract_bom_rows`. The latter reads BLOCK
        # attributes and returns nothing on these drawings, whose BOM is a drawn table; the
        # orchestrator calls the table extractor for exactly that reason
        # (`orchestrator.py:421`). Picking the wrong one here yields an empty value set and
        # silently disables every `bill_of_materials` mutation.
        from ..audit.bom.table_extractor import extract_bom_table

        rows, _is_assembly = extract_bom_table(
            entities, render_bounds=None, bom_bbox=regions.get("bom")
        )
    except Exception:
        return set()
    values: set[str] = set()
    for row in rows:
        for value in (row or {}).values():
            text = str(value or "").strip()
            if text and text.upper() != "NONE":
                values.add(text)
    return values


def _bump_digits(text: str, rng: random.Random) -> str:
    """Change the first number in a string, keeping its shape.

    Shape matters: `%%c120` → `%%c125` stays a diameter callout, so the mutation reads as
    an engineering change rather than as corrupt text.
    """
    match = _DIGITS.search(text)
    if not match:
        return text + rng.choice(["A", "B", "2"])
    original = match.group(0)
    value = int(original)
    delta = rng.choice([1, 2, 5, 10, -1, -5])
    bumped = max(0, value + delta)
    replacement = str(bumped).rjust(len(original), "0") if len(original) > 1 else str(bumped)
    return text[: match.start()] + replacement + text[match.end() :]


def _retarget_number(text: str, value: float) -> str:
    """Rewrite the first number in `text` to `value`, keeping any prefix/suffix.

    `%%c120` with a new measurement of 122.5 becomes `%%c122.5` — still a diameter
    callout, and still agreeing with the measurement the differ compares on.
    """
    formatted = f"{value:g}"
    match = _DIGITS.search(text)
    if not match:
        return formatted
    # Extend the match over a decimal tail so `22.7` is replaced whole, not just `22`.
    end = match.end()
    if end < len(text) and text[end] == "." and text[end + 1 : end + 2].isdigit():
        end += 1
        while end < len(text) and text[end].isdigit():
            end += 1
    return text[: match.start()] + formatted + text[end:]


def _pick_zone(mutator: Mutator, rng: random.Random, entities: list[EvalEntity], zones: list[str]):
    """A (zone, targets) pair for the first zone offering something to edit."""
    order = [z for z in zones if z in mutator.zones]
    rng.shuffle(order)
    for zone in order:
        targets = mutator.candidates(entities, zone)
        if targets:
            return zone, targets
    return None, []


def op_edit_text(mutator, rng, entities, pending, ocr) -> str | None:
    """Edit a text run in place — one editorial act, one CHANGED finding."""
    zone, targets = _pick_zone(mutator, rng, entities, ["notes", "views", "bom", "iso"])
    if not targets:
        return None
    target = rng.choice(targets)
    before = _text_of(target)
    after = _bump_digits(before, rng)
    if after == before:
        return None
    target.properties["text"] = after
    pending.append(
        _Pending(
            side="REV",
            category=ZONE_CATEGORY[zone],
            status="CHANGED",
            ref_text=before,
            rev_text=after,
            notes=f"edit_text in zone '{zone}'",
            entity=target,
        )
    )
    return f"{before!r} -> {after!r}"


def op_delete_text(mutator, rng, entities, pending, ocr) -> str | None:
    """Remove a text run. Anchored on the reference side, per the guideline."""
    zone, targets = _pick_zone(mutator, rng, entities, ["notes", "views", "bom"])
    if not targets:
        return None
    target = rng.choice(targets)
    # The reference index is what the label anchors to, and the reference list is never
    # mutated — so this is found by matching the untouched base, not the working copy.
    ref_index = _base_index_of(mutator, target)
    if ref_index < 0:
        return None
    entities.remove(target)
    pending.append(
        _Pending(
            side="REF",
            category=ZONE_CATEGORY[zone],
            status="REMOVED",
            ref_text=_text_of(target),
            rev_text="",
            notes=f"delete_text in zone '{zone}'",
            ref_index=ref_index,
        )
    )
    return f"deleted {_text_of(target)!r}"


def op_insert_text(mutator, rng, entities, pending, ocr) -> str | None:
    """Add a new text run beside an existing one."""
    zone, targets = _pick_zone(mutator, rng, entities, ["notes", "views", "bom"])
    if not targets:
        return None
    neighbour = rng.choice(targets)
    point = mutator._anchor(neighbour) or (0.0, 0.0)
    text = rng.choice(["追加注記", "※ 要確認", "NEW NOTE", "追加 3-M8"])
    added = EvalEntity(
        entity_type="text",
        layer=neighbour.layer,
        handle=None,
        properties={"text": text, "height": neighbour.properties.get("height")},
        geometry={"insert": [float(point[0]) + 2.0, float(point[1]) - 6.0]},
    )
    entities.append(added)
    pending.append(
        _Pending(
            side="REV",
            category=ZONE_CATEGORY[zone],
            status="ADDED",
            ref_text="",
            rev_text=text,
            notes=f"insert_text in zone '{zone}'",
            entity=added,
        )
    )
    return f"inserted {text!r}"


def op_edit_dimension_measurement(mutator, rng, entities, pending, ocr) -> str | None:
    """Change a dimension's measured value — a real engineering change.

    The differ keys a dimension on `dim:{kind}:{measurement}`, never on display text, so
    `measurement` is what has to move for this to be a change at all. Its text override is
    updated to match, because a dimension whose text and measurement disagree is a
    different (and confusing) test.
    """
    box = mutator.zones.get("views")
    if not box:
        return None
    targets = [
        e
        for e in entities
        if e.entity_type == "dimension"
        and e.properties.get("measurement") is not None
        and mutator._in_box(e, box)
        and not mutator._in_safe_zone(e)
    ]
    if not targets:
        return None
    target = rng.choice(targets)
    before_value = float(target.properties["measurement"])
    after_value = round(before_value + rng.choice([1.0, 2.5, 5.0, -1.0, -2.5]), 3)
    if after_value <= 0 or after_value == before_value:
        return None
    before_text = _text_of(target)
    target.properties["measurement"] = after_value
    if before_text:
        # Derived from the new measurement, not bumped independently. Two separate random
        # draws produced dimensions whose text said 125 while their measurement said 119 —
        # incoherent as a drawing, and a label whose `rev_text` contradicted the thing the
        # differ actually compares.
        target.properties["text"] = _retarget_number(before_text, after_value)
    pending.append(
        _Pending(
            side="REV",
            category="drawing_views",
            status="CHANGED",
            ref_text=before_text or f"{before_value:g}",
            rev_text=_text_of(target) or f"{after_value:g}",
            notes=f"measurement {before_value:g} -> {after_value:g}",
            entity=target,
        )
    )
    return f"{before_value:g} -> {after_value:g}"


def op_edit_title_field(mutator, rng, entities, pending, ocr) -> str | None:
    """Edit a title-block field, and the OCR cache entry that would otherwise mask it.

    `extract_title_block` prefers a cached OCR value over the spatial reading, so editing
    only the entity would produce a label the engine cannot possibly satisfy. The pair's
    derived OCR entry is edited in step; when the drawing has no OCR to derive from, the
    operator declines rather than emitting a label it knows is unreachable.
    """
    if ocr is None:
        return None
    box = mutator.zones.get("title")
    if not box:
        return None

    fields = [f for f in OCR_FIELDS if str(ocr.get(f) or "").strip()]
    rng.shuffle(fields)
    for field_name in fields:
        value = str(ocr[field_name]).strip()
        matches = [
            e
            for e in entities
            if e.entity_type == "text"
            and _text_of(e).strip() == value
            and mutator._in_box(e, box)
        ]
        if len(matches) != 1:
            # Zero means OCR read something no single text run carries (a value split
            # across runs); more than one means the edit would be ambiguous. Either way
            # this field cannot be mutated cleanly.
            continue
        target = matches[0]
        after = _bump_digits(value, rng)
        if after == value:
            continue
        target.properties["text"] = after
        ocr[field_name] = after
        pending.append(
            _Pending(
                side="REV",
                category="title_block",
                status="CHANGED",
                ref_text=value,
                rev_text=after,
                notes=f"title field {field_name}, OCR cache derived in step",
                entity=target,
            )
        )
        return f"{field_name}: {value!r} -> {after!r}"
    return None


def op_null_mutation(mutator, rng, entities, pending, ocr) -> str | None:
    """Change nothing. Ground truth is zero findings.

    Every finding an engine reports on this pair is a false positive, measured rather than
    argued. Cheapest precision number available and the first one this project can produce.
    """
    return "no change"


def op_restyle_dimension_text(mutator, rng, entities, pending, ocr) -> str | None:
    """Rewrite a dimension's display override without touching its measurement.

    `%%c120` and a dimension-style default both render ⌀120. Per the annotation guideline
    that is a transcoding, not a change, and the differ compares `measurement` for exactly
    this reason. Emits **no finding** — this is a precision probe aimed at the regression
    where display text creeps back into the comparison key.
    """
    box = mutator.zones.get("views")
    if not box:
        return None
    targets = [
        e
        for e in entities
        if e.entity_type == "dimension"
        and e.properties.get("measurement") is not None
        and _text_of(e).strip()
        and mutator._in_box(e, box)
    ]
    if not targets:
        return None
    target = rng.choice(targets)
    before = _text_of(target)
    measurement = float(target.properties["measurement"])
    after = "" if before.startswith("%%c") else f"%%c{measurement:g}"
    if after == before:
        return None
    target.properties["text"] = after
    return f"restyled {before!r} -> {after!r} (measurement unchanged)"


def op_translate_entities(mutator, rng, entities, pending, ocr) -> str | None:
    """Nudge a cluster of text without editing it.

    The guideline: pure relocation with identical text is not a finding. Emits **no
    finding**. The offset is small on purpose — a large one would push entities out of the
    views box, at which point the engine is *right* to report them, and the probe would be
    measuring the wrong thing.
    """
    zone, targets = _pick_zone(mutator, rng, entities, ["views", "notes"])
    if not targets:
        return None
    dx, dy = rng.uniform(-3.0, 3.0), rng.uniform(-3.0, 3.0)
    moved = 0
    for entity in targets[: max(1, len(targets) // 4)]:
        point = entity.geometry.get("insert") or entity.geometry.get("location")
        if not point or len(point) < 2:
            continue
        entity.geometry["insert"] = [float(point[0]) + dx, float(point[1]) + dy] + list(point[2:])
        moved += 1
    return f"moved {moved} entity(ies) by ({dx:.2f}, {dy:.2f})" if moved else None


def _base_index_of(mutator: Mutator, entity: EvalEntity) -> int:
    """Locate a working-copy entity in the untouched base list.

    Matched on handle when one exists, otherwise on type + text + position, which is
    unique in practice because two identical strings at the same coordinates would be
    duplicate geometry. Returns -1 rather than guessing.
    """
    if entity.handle:
        for index, base in enumerate(mutator.base_entities):
            if base.handle == entity.handle:
                return index
    text = _text_of(entity)
    point = entity.geometry.get("insert") or entity.geometry.get("location") or []
    matches = [
        index
        for index, base in enumerate(mutator.base_entities)
        if base.entity_type == entity.entity_type
        and _text_of(base) == text
        and (base.geometry.get("insert") or base.geometry.get("location") or []) == list(point)
    ]
    return matches[0] if len(matches) == 1 else -1


OPERATORS: dict[str, Operator] = {
    "edit_text": op_edit_text,
    "delete_text": op_delete_text,
    "insert_text": op_insert_text,
    "edit_dimension_measurement": op_edit_dimension_measurement,
    "edit_title_field": op_edit_title_field,
    "null_mutation": op_null_mutation,
    "restyle_dimension_text": op_restyle_dimension_text,
    "translate_entities": op_translate_entities,
}

# Relative draw weights for a random pair. `null_mutation` is excluded: it is drawn as a
# whole pair in `_pick_operators`, because "zero findings" only means something when
# nothing else ran alongside it.
OPERATOR_WEIGHTS: dict[str, int] = {
    "edit_text": 4,
    "delete_text": 2,
    "insert_text": 2,
    "edit_dimension_measurement": 3,
    "edit_title_field": 2,
    "restyle_dimension_text": 2,
    "translate_entities": 2,
}

# Operators whose ground truth is "no finding". Reported separately by the scorer: they
# measure precision only, and folding them into a recall denominator would divide by zero.
ZERO_FINDING_OPERATORS = frozenset(
    {"null_mutation", "restyle_dimension_text", "translate_entities"}
)


def ocr_cache_payload(pair: MutationPair) -> str | None:
    """The derived title-block OCR entry for a mutated side, ready to write to cache."""
    if pair.ocr_override is None:
        return None
    return json.dumps(pair.ocr_override, ensure_ascii=False, indent=2)
