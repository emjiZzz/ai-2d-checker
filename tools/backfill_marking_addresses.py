#!/usr/bin/env python
"""Repair `layer` and `text` on stored ground-truth marking addresses.

    services/backend/.venv/Scripts/python.exe tools/backfill_marking_addresses.py
    ... tools/backfill_marking_addresses.py --apply

An address is meant to hold what the DXF holds, so it survives re-extraction. Two fields did not:
`layer` was always "0", and `text` held the decoded display string where the file says `%%c265x25`.
Neither breaks tier 1, which matches on `handle` alone; tiers 2 and 3 compare layer and text, and
that is where block-exploded children -- most of the reference sheets -- resolve.

Both are recoverable without guessing, from the keys the resolver itself trusts. Control-code
decoding is a fallback locator, used only after an exact match fails and only when it names exactly
one entity. Anything ambiguous or absent is reported and skipped.

Reports only unless `--apply`. It writes `layer` and `text` and nothing else.
See `06 - .../Gotcha - An Address That Read Perfectly and Resolved to Nothing.md` for the causes.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SIDES = ("ref_address", "rev_address")

# AutoCAD's in-string control codes. The frontend renders these; the DXF stores them. Kept here
# rather than shared with `ai_engine._clean` because that one maps %%c to U+00D8 and the picker
# produces U+2300 -- a disagreement worth recording before it is unified, not silently inheriting.
CONTROL_CODES = {
    "%%c": "⌀",
    "%%C": "⌀",
    "%%d": "°",
    "%%D": "°",
    "%%p": "±",
    "%%P": "±",
}


def decode(value: str | None) -> str:
    out = value or ""
    for code, glyph in CONTROL_CODES.items():
        out = out.replace(code, glyph)
    return out


def entity_text(entity: dict[str, Any]) -> str | None:
    return (entity.get("properties") or {}).get("text")


def locate(
    address: dict[str, Any], entities: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    """The live entity this address names, or a reason it cannot be named without guessing."""
    from services.backend.infrastructure.ground_truth.address_resolver import _norm

    handle = address.get("handle")
    if handle:
        hit = next((e for e in entities if e.get("handle") == handle), None)
        return (hit, "handle") if hit else (None, "handle absent from drawing")

    parent = address.get("parent_handle")
    if not parent:
        return None, "no handle and no parent_handle"

    siblings = [
        e
        for e in entities
        if e.get("parent_handle") == parent and e.get("entity_type") == address.get("entity_type")
    ]
    wanted = _norm(address.get("text"))
    exact = [e for e in siblings if entity_text(e) == address.get("text")]
    if len(exact) == 1:
        return exact[0], "parent_handle"
    decoded = [e for e in siblings if _norm(decode(entity_text(e))) == wanted]
    if len(decoded) == 1:
        return decoded[0], "parent_handle (control codes decoded)"
    hits = decoded or exact
    return None, f"parent_handle names {len(hits)} candidates"


async def collect(db: Any) -> tuple[list[dict[str, Any]], collections.Counter, list[tuple]]:
    markings = await db["ground_truth_markings"].find({"retracted_at": None}).to_list(length=100_000)
    entities_by_drawing: dict[str, list[dict[str, Any]]] = {}
    repairs: list[dict[str, Any]] = []
    tally: collections.Counter = collections.Counter()
    skipped: list[tuple] = []

    for marking in markings:
        for side in SIDES:
            address = marking.get(side)
            if not address:
                continue
            tally["addresses"] += 1
            drawing_id = address.get("drawing_id")
            if not drawing_id:
                tally["skipped"] += 1
                skipped.append((str(marking.get("_id")), side, "address has no drawing_id"))
                continue
            if drawing_id not in entities_by_drawing:
                entities_by_drawing[drawing_id] = await db["extracted_entities"].find(
                    {"drawing_id": drawing_id}
                ).to_list(length=100_000)
            entity, how = locate(address, entities_by_drawing[drawing_id])
            if entity is None:
                tally["skipped"] += 1
                skipped.append((str(marking.get("_id")), side, how))
                continue

            changes: dict[str, Any] = {}
            actual_layer = str(entity.get("layer"))
            if actual_layer != str(address.get("layer")):
                changes[f"{side}.layer"] = actual_layer
            actual_text = entity_text(entity)
            if actual_text is not None and actual_text != address.get("text"):
                changes[f"{side}.text"] = actual_text
            if not changes:
                tally["already correct"] += 1
                continue
            tally["to repair"] += 1
            for field in changes:
                tally[f"  field {field.split('.')[-1]}"] += 1
            repairs.append({"_id": marking.get("_id"), "changes": changes, "how": how})

    return repairs, tally, skipped


async def run(apply: bool) -> int:
    from services.backend.infrastructure.database.connection import db_manager

    await db_manager.connect()
    db = db_manager.db
    repairs, tally, skipped = await collect(db)

    for key in ("addresses", "already correct", "to repair", "  field layer", "  field text", "skipped"):
        print(f"  {key:20s} {tally[key]}")

    by_how: collections.Counter = collections.Counter(r["how"] for r in repairs)
    print(f"\n  located by: {dict(by_how)}")

    if skipped:
        reasons = collections.Counter(reason for _, _, reason in skipped)
        print(f"\n  skipped {len(skipped)}, by reason:")
        for reason, n in reasons.most_common():
            print(f"    {reason:44s} {n}")
        print("  These keep their stored values and stay unresolvable: a countable gap, not a guess.")

    if not apply:
        print("\n  Dry run. Re-run with --apply to write.")
        return 0

    written = 0
    for repair in repairs:
        result = await db["ground_truth_markings"].update_one(
            {"_id": repair["_id"]}, {"$set": repair["changes"]}
        )
        written += result.modified_count
    print(f"\n  wrote {written} marking(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repairs (default: report)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
