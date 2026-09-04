#!/usr/bin/env python
"""Address-resolution census: does a click land on the entity the engineer meant?

## Why this exists

`render_audit.py` exists because judging the vector canvas by eye failed twice. This is the
same harness for the *other* pipeline that fails silently -- ground-truth addressing.

A manual-check marking stores an `EntityAddress`; `address_resolver` re-binds it to a live
entity; `manual_check_bridge` turns that into a corpus label. Every step reads perfectly when
it is wrong. A mis-resolved marking does not error, does not look odd, and cannot be detected
downstream: it simply attributes a person's judgement to the wrong entity, forever, in a file
that is then used as ground truth.

Measured 2026-08-20, before the fix that prompted this tool: **33 of 3673 converted REMOVED
findings landed on the wrong entity**, one of them at distance 0.0 -- the strongest match the
resolver can express. It survived design, implementation and review because **every one of the
1541 TEXT entities resolved correctly**, and the unit tests, the committed labels and the
feature demo were all text.

The unit tests in `tests/test_ground_truth_addressing.py` pin the rules against hand-built
fakes. Fakes cannot reproduce two border lines sharing a corner or three concentric arcs
sharing a centre, which is the geometry that actually broke. **This runs against real frozen
payloads.**

## What it reports

1. **Per-entity-type resolution** -- correct / wrong / unresolved, and the `MatchTier` mix.
   Read this column-wise: a type at 100% next to a type at 19% is the shape of the defect this
   tool was built for, and it is invisible in any aggregate.

2. **Round trip through the bridge** -- takes the address `build_labels` actually emits and
   asks whether it resolves back to the entity that was picked. Resolution being right is not
   the same claim as the emitted label being right, and only the second one is what lands in
   the corpus.

3. **Ambiguity refusals** -- coincident geometry the address cannot separate, which
   `_nearest` now declines to guess at. Reported so the cost of refusing stays visible rather
   than looking like a silent loss of recall.

## The one thing that must not be got wrong

**Probe with a realistic click, not with the entity's own anchor.**

`EntityAddress.point` is where the engineer clicked -- `useEntityPicking` sends the pointer's
world position verbatim. Probing each entity at its canonical anchor (`start`, `center`) is the
best case, makes every number look excellent, and hides the entire defect class: the whole bug
was that a click and an anchor are different quantities. So a line is clicked at its midpoint,
a curve on its circumference, a polyline on its first span.

An ellipse must be probed on its `points` run. Its `center` is not on its own outline, so
anchoring there produces "wrong" rows that are artifacts of the probe rather than defects in
the resolver -- 24 of them on the one sheet where that was tried.

## Verified against the defect it was built for

Reverting `_entity_distance` in `address_resolver.py` must make this report ~59% correct and
33 wrong. A census that cannot show the bug it exists for is not a census -- see
`Gotcha - A Guard Test's Failure Path Had Never Run`.

Usage:

    services/backend/.venv/Scripts/python.exe tools/address_audit.py
    services/backend/.venv/Scripts/python.exe tools/address_audit.py --sample 6 --json out.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.domain.models.ground_truth import EntityAddress  # noqa: E402
from services.backend.infrastructure.audit.comparison.spatial_differ import (  # noqa: E402
    SpatialDiffer,
)
from services.backend.infrastructure.eval.corpus import load_corpus  # noqa: E402
from services.backend.infrastructure.eval.manual_check_bridge import build_labels  # noqa: E402
from services.backend.infrastructure.ground_truth.address_resolver import resolve  # noqa: E402

#: Entity types that carry no drawable geometry and are therefore not clickable. Counted in
#: their own bucket rather than folded into "unresolved", for the same reason `render_audit`
#: gives the section-callout cull its own bucket: a deliberate exclusion inside a shortfall is
#: how a harness that exists to detect loss stops being able to.
NOT_PICKABLE = {"layer", "block"}


def _xy(raw: Any) -> tuple[float, float] | None:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
    return None


def click_point(entity: Any) -> tuple[float, float] | None:
    """Where a person plausibly clicks to select this entity.

    Ordered so that a shape is probed on the geometry it draws, never on a derived anchor.
    `points` is checked before `center` because an ellipse carries both and its centre is not
    on its outline.
    """
    geometry = getattr(entity, "geometry", None) or {}

    start, end = _xy(geometry.get("start")), _xy(geometry.get("end"))
    if start and end:
        return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)

    for key in ("points", "vertices", "fit_points"):
        run = geometry.get(key)
        if isinstance(run, list) and len(run) >= 2:
            first, second = _xy(run[0]), _xy(run[1])
            if first and second:
                return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)

    center, radius = _xy(geometry.get("center")), geometry.get("radius")
    if center and radius:
        try:
            r = float(radius)
        except (TypeError, ValueError):
            r = None
        if r:
            return (center[0] + r * math.cos(math.pi / 4), center[1] + r * math.sin(math.pi / 4))

    paths = geometry.get("render_paths")
    if isinstance(paths, list):
        for path in paths:
            if isinstance(path, list) and len(path) >= 2:
                first, second = _xy(path[0]), _xy(path[1])
                if first and second:
                    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)

    for key in ("insert", "text_point", "def_point", "center", "location"):
        point = _xy(geometry.get(key))
        if point:
            return point
    return None


def address_for(entity: Any, drawing_id: str, point: tuple[float, float]) -> EntityAddress:
    """The address the app would store for this pick.

    Mirrors `createManualCheckSlice.toAddress` field for field, plus the `point` the router
    stamps server-side. Built here rather than imported because the app-side constructor is
    TypeScript; `tests/test_ground_truth_addressing.py` pins the shape against
    `ExtractedEntity` so the two cannot drift apart unnoticed.
    """
    return EntityAddress(
        drawing_id=drawing_id,
        handle=getattr(entity, "handle", None),
        parent_handle=getattr(entity, "parent_handle", None),
        entity_type=str(getattr(entity, "entity_type", "") or "").lower(),
        layer=str(getattr(entity, "layer", "0") or "0"),
        text=SpatialDiffer._get_entity_text(entity),
        point=list(point),
    )


def probe_pair(pair: Any, step: int) -> dict[str, Any]:
    """Simulate a REMOVED stamp on every (or every `step`-th) reference entity of one pair.

    REMOVED is the interesting side: it anchors on the reference, which is where handle
    coverage collapses (0.8-13% on this client's sheets, because the content lives inside
    blocks and `virtual_entities()` yields handle-less copies). ADDED and CHANGED anchor on the
    revision and lean on handles, so they exercise tier 1 and prove much less.
    """
    _ref_drawing, _rev_drawing, ref_entities, rev_entities = pair.load()

    by_type: dict[str, Counter] = defaultdict(Counter)
    tiers: Counter = Counter()
    markings: list[dict[str, Any]] = []
    probed: list[tuple[int, Any]] = []

    for index, entity in enumerate(ref_entities):
        if index % step:
            continue
        etype = str(getattr(entity, "entity_type", "") or "?").lower()

        point = click_point(entity)
        if point is None:
            # A layer record or block container draws nothing, so no click could select it.
            # Its own bucket, never folded into `unresolved`: a deliberate exclusion hidden
            # inside a shortfall is how a harness that exists to detect loss stops being able
            # to -- the same reason `render_audit` gives its section-callout cull a bucket.
            by_type[etype]["not_pickable" if etype in NOT_PICKABLE else "unresolved"] += 1
            continue

        address = address_for(entity, pair.ref.drawing_id, point)
        resolution = resolve(address, ref_entities)
        tiers[resolution.tier.value] += 1

        if not resolution.ok:
            by_type[etype]["unresolved"] += 1
            continue
        if resolution.entity is not entity:
            by_type[etype]["wrong"] += 1
            continue

        by_type[etype]["correct"] += 1
        probed.append((index, entity))
        markings.append(
            {
                "_id": f"m{index}",
                "status": "REMOVED",
                "category": "notes_section",
                "ref_address": address.model_dump(),
                "rev_address": None,
                "ref_text": SpatialDiffer._get_entity_text(entity),
                "rev_text": "",
                "notes": "",
                "is_bulk": False,
                "retracted_at": None,
            }
        )

    # -- the round trip -----------------------------------------------------
    # Resolution being right is a different claim from the emitted label being right. Only
    # findings whose resolution already succeeded are carried here, so a failure in this block
    # is specifically a bridge/addressing defect and not a resolver one.
    round_trip = {"checked": 0, "correct": 0, "wrong": 0, "unaddressable": 0}
    if markings:
        result = build_labels(
            pair_id=pair.pair_id,
            markings=markings,
            ref_entities=ref_entities,
            rev_entities=rev_entities,
            annotator="address_audit",
            annotated_at="1970-01-01",
        )
        lost = {u.marking_id for u in result.unresolved}
        kept = [(i, e) for (i, e) in probed if f"m{i}" not in lost]
        for (_index, original), finding in zip(kept, result.labels.findings, strict=False):
            round_trip["checked"] += 1
            landed = finding.resolve(ref_entities, rev_entities)
            if landed is None:
                round_trip["unaddressable"] += 1
            elif landed is original:
                round_trip["correct"] += 1
            else:
                round_trip["wrong"] += 1

    handles = sum(1 for e in ref_entities if getattr(e, "handle", None))
    return {
        "pair_id": pair.pair_id,
        "ref_entities": len(ref_entities),
        "ref_handle_coverage": handles / len(ref_entities) if ref_entities else 0.0,
        "by_type": {k: dict(v) for k, v in sorted(by_type.items())},
        "tiers": dict(tiers),
        "round_trip": round_trip,
    }


def _totals(pairs: list[dict[str, Any]]) -> dict[str, Counter]:
    merged: dict[str, Counter] = defaultdict(Counter)
    for pair in pairs:
        for etype, counts in pair["by_type"].items():
            merged[etype].update(counts)
    return merged


def print_report(result: dict[str, Any]) -> None:
    pairs = result["pairs"]
    merged = _totals(pairs)

    print(f"\n=== ADDRESS CENSUS === {len(pairs)} pair(s), probed with a realistic click\n")
    print(f"  {'TYPE':<12} {'N':>6} {'CORRECT':>9} {'WRONG':>7} {'UNRESOLVED':>11}  NOTE")

    grand = Counter()
    for etype, counts in sorted(merged.items(), key=lambda kv: -sum(
        kv[1][k] for k in ("correct", "wrong", "unresolved")
    )):
        correct, wrong = counts["correct"], counts["wrong"]
        unresolved = counts["unresolved"]
        n = correct + wrong + unresolved
        if not n:
            continue
        grand.update({"correct": correct, "wrong": wrong, "unresolved": unresolved, "n": n})
        pct = f"{100 * correct / n:.1f}%" if n else "-"
        note = "not pickable" if counts.get("not_pickable") else ""
        flag = "  <-- WRONG" if wrong else ""
        print(
            f"  {etype:<12} {n:>6} {pct:>9} {wrong:>7} {unresolved:>11}  {note}{flag}"
        )

    n = grand["n"] or 1
    print(f"\n  {'ALL':<12} {grand['n']:>6} {100 * grand['correct'] / n:>8.1f}% "
          f"{grand['wrong']:>7} {grand['unresolved']:>11}")

    # Shown rather than silently absent from the table above. These records draw nothing, so
    # "0 correct" would be a false indictment and omitting them would be a false denominator.
    unpickable = {t: c["not_pickable"] for t, c in sorted(merged.items()) if c.get("not_pickable")}
    if unpickable:
        detail = ", ".join(f"{t} {n_}" for t, n_ in unpickable.items())
        # ASCII only: this prints to a cp932/cp1252 console on the machines that run it, where
        # an em dash arrives as a literal '?'.
        print(f"  {'(unpickable)':<12} {sum(unpickable.values()):>6}   {detail} - draw nothing")

    tiers: Counter = Counter()
    for pair in pairs:
        tiers.update(pair["tiers"])
    if tiers:
        print("\n  resolved by tier:  " + ", ".join(f"{k} {v}" for k, v in sorted(tiers.items())))

    rt = Counter()
    for pair in pairs:
        rt.update(pair["round_trip"])
    print(
        f"\n  ROUND TRIP through build_labels -- does the EMITTED address point back?\n"
        f"    checked {rt['checked']}   correct {rt['correct']}   "
        f"wrong {rt['wrong']}   unaddressable {rt['unaddressable']}"
    )

    if grand["wrong"] or rt["wrong"]:
        print(
            "\n  [!] A non-zero WRONG column is the failure this tool exists for: the resolver\n"
            "      returned an entity the engineer did not pick, with no error and no signal.\n"
            "      Expected value is 0."
        )
    else:
        print("\n  No entity was mis-attributed. Unresolved rows are reported, never guessed.")

    print(f"\n  {'PAIR':<26} {'REF ENTS':>9} {'HANDLES':>8}  ROUND TRIP")
    for pair in pairs:
        rtp = pair["round_trip"]
        print(
            f"  {pair['pair_id']:<26} {pair['ref_entities']:>9} "
            f"{100 * pair['ref_handle_coverage']:>7.1f}%  "
            f"{rtp['correct']}/{rtp['checked']}"
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--sample",
        type=int,
        default=1,
        metavar="N",
        help="Probe every Nth reference entity (default 1 = every entity).",
    )
    parser.add_argument(
        "--pair-id", action="append", default=None, help="Limit to these pairs (repeatable)."
    )
    parser.add_argument(
        "--provenance",
        choices=("human", "mutation"),
        default="human",
        help="Which pairs to census when none are named. Defaults to human: mutation pairs "
        "share one reference sheet, so they inflate every count without adding a case.",
    )
    parser.add_argument(
        "--include-held-out",
        action="store_true",
        help="Include held-out pairs. Requires --reason; the access is logged.",
    )
    parser.add_argument("--reason", default="", help="Why held-out pairs are being read.")
    parser.add_argument("--json", type=Path, default=None, help="Write the full census here.")
    args = parser.parse_args()

    if args.include_held_out and not args.reason.strip():
        parser.error("--include-held-out requires --reason; the access is logged.")

    corpus = load_corpus(
        include_held_out=args.include_held_out,
        held_out_reason=args.reason,
    )

    wanted = set(args.pair_id or [])
    pairs = []
    skipped: list[tuple[str, str]] = []
    for pair in corpus.pairs:
        if wanted and pair.pair_id not in wanted:
            continue
        # Mutation pairs re-use one reference sheet dozens of times, so including them
        # multiplies a single underlying case into a headline number: the first run of this
        # tool reported 25 "pairs" of which 20 were one sheet counted over. Filter on the
        # corpus's own `provenance` rather than on the id -- the mutation ids are `-ref-mut`,
        # not the `-rev-` a name-based guess expects, which is exactly how that slipped through.
        if not wanted and pair.provenance != args.provenance:
            continue
        try:
            pairs.append(probe_pair(pair, max(1, args.sample)))
        except Exception as err:  # noqa: BLE001 - an unreadable payload is a reportable row
            skipped.append((pair.pair_id, f"{type(err).__name__}: {err}"))

    if not pairs:
        print("No pairs censused.", file=sys.stderr)
        return 2

    result = {"sample_step": args.sample, "pairs": pairs, "skipped": skipped}
    print_report(result)

    if skipped:
        print(f"  [!] {len(skipped)} pair(s) could not be read:")
        for pair_id, err in skipped:
            print(f"      {pair_id}: {err}")
        print()

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Census written to {args.json}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
