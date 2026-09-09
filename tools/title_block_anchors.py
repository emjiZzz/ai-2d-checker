#!/usr/bin/env python
"""Where the title block and BOM actually sit, measured from ground-truth markings.

    services/backend/.venv/Scripts/python.exe tools/title_block_anchors.py
    ... tools/title_block_anchors.py --write-fixture   # regenerate the committed observations

Reads the live `ground_truth_markings` collection and reports each marked field's offset from
every sheet edge, in drawing units. Read-only; it opens no writes.

The reason this tool exists rather than a fraction table: normalising a position by
`render_bounds` divides by a denominator that differs between paper sizes, which makes one
drawing template look like several. Measured from a sheet corner instead, the A3 sheets in this
corpus agree to 0.00 units.
See `06 - .../Gotcha - One Template Looked Like Several in Fraction Space.md` in the vault.

`--write-fixture` writes observations only, never derived constants. The rules that turn them
into anchors live in `tests/test_title_block_anchors.py`, so a rule change is a diff in the test
rather than a silent change in a regenerated JSON blob.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "title_block" / "anchor_observations.json"

# Categories whose fields are furniture pinned to the sheet frame. `drawing_views` is
# deliberately absent: its content moves with the revision, which is the thing being compared.
ANCHORED_CATEGORIES = ("title_block", "bill_of_materials", "notes_section")

# `render_bounds` is the ISO sheet plus a 5% margin on every side. Pinned in the test, restated
# here only so the report can print the sheet size it implies.
BOUNDS_INFLATION = 1.1


def offsets(point: dict[str, Any], bounds: list[float]) -> dict[str, float]:
    """Distance from each edge of `render_bounds`, in drawing units."""
    return {
        "left": point["x"] - bounds[0],
        "right": bounds[2] - point["x"],
        "bottom": point["y"] - bounds[1],
        "top": bounds[3] - point["y"],
    }


def observation(marking: dict[str, Any], side: str) -> dict[str, Any] | None:
    address = marking.get(side) or {}
    point = address.get("point") or {}
    bounds = point.get("bounds")
    if not bounds or len(bounds) != 4:
        return None
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    if not width or not height:
        return None
    return {
        "category": marking.get("category"),
        "feature": marking.get("feature"),
        "side": "ref" if side == "ref_address" else "rev",
        "space": point.get("space"),
        "room_id": str(marking.get("room_id")),
        "drawing_id": str(address.get("drawing_id")),
        "bounds_width": round(width, 4),
        "bounds_height": round(height, 4),
        "offsets": {edge: round(value, 4) for edge, value in offsets(point, bounds).items()},
        "fraction": {
            "fx": round((point["x"] - bounds[0]) / width, 6),
            "fy": round((point["y"] - bounds[1]) / height, 6),
        },
    }


async def collect() -> list[dict[str, Any]]:
    from services.backend.infrastructure.database.connection import db_manager

    await db_manager.connect()
    markings = await db_manager.db["ground_truth_markings"].find({}).to_list(length=100_000)
    rows = []
    for marking in markings:
        if marking.get("retracted_at") or marking.get("category") not in ANCHORED_CATEGORIES:
            continue
        for side in ("ref_address", "rev_address"):
            row = observation(marking, side)
            if row and row["space"] == "paper":
                rows.append(row)
    return rows


def best_anchor(rows: list[dict[str, Any]], axis_edges: tuple[str, str]) -> tuple[str, float]:
    """Which edge a field is fixed to, and the spread that remains against it.

    Pooled across paper sizes on purpose. Within one size the two edges of an axis are perfectly
    correlated, so grouping first scores both edges identically and the answer is arbitrary.
    """
    scored = [(st.pstdev([row["offsets"][edge] for row in rows]), edge) for edge in axis_edges]
    spread, edge = min(scored)
    return edge, spread


def within_size_spread(rows: list[dict[str, Any]], edge: str) -> float:
    """Spread against `edge` within one paper size: whether the template is stable at all."""
    by_size = defaultdict(list)
    for row in rows:
        by_size[row["bounds_width"]].append(row["offsets"][edge])
    spreads = [st.pstdev(v) for v in by_size.values() if len(v) > 1]
    return max(spreads) if spreads else 0.0


def report(rows: list[dict[str, Any]]) -> None:
    sizes = sorted({(r["bounds_width"], r["bounds_height"]) for r in rows}, reverse=True)
    print(f"paper-space sheets: {len(sizes)}  observations: {len(rows)}\n")
    for width, height in sizes:
        n = sum(1 for r in rows if r["bounds_width"] == width)
        sheet = f"{width / BOUNDS_INFLATION:7.1f} x {height / BOUNDS_INFLATION:6.1f}"
        print(f"  bounds {width:8.1f} x {height:7.1f}   sheet {sheet}   n={n}")

    by_feature = defaultdict(list)
    for row in rows:
        by_feature[(row["category"], row["feature"])].append(row)

    print(
        f"\n{'category':18s} {'feature':24s} {'n':>3} {'anchor':>13s} "
        f"{'within-size':>12s} {'pooled':>8s} {'fraction sd':>16s}"
    )
    for (category, feature), group in sorted(by_feature.items(), key=lambda kv: -len(kv[1])):
        if len(group) < 3:
            continue
        x_edge, x_spread = best_anchor(group, ("left", "right"))
        y_edge, y_spread = best_anchor(group, ("bottom", "top"))
        fx_sd = st.pstdev([r["fraction"]["fx"] for r in group])
        fy_sd = st.pstdev([r["fraction"]["fy"] for r in group])
        wx = within_size_spread(group, x_edge)
        wy = within_size_spread(group, y_edge)
        print(
            f"{str(category)[:18]:18s} {str(feature)[:24]:24s} {len(group):3d} "
            f"{x_edge + '/' + y_edge:>13s} {f'{wx:.2f},{wy:.2f}':>12s} "
            f"{f'{x_spread:.0f},{y_spread:.0f}':>8s} {f'{fx_sd:.4f},{fy_sd:.4f}':>16s}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-fixture", action="store_true", help=f"rewrite {FIXTURE}")
    parser.add_argument("--json", action="store_true", help="print observations as JSON")
    args = parser.parse_args()

    rows = asyncio.run(collect())
    if not rows:
        print("No paper-space markings found in anchored categories. Nothing to measure.")
        return 1

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    report(rows)
    if args.write_fixture:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "note": "Observations only. The anchor rules live in "
            "tests/test_title_block_anchors.py.",
            "regenerate": "services/backend/.venv/Scripts/python.exe "
            "tools/title_block_anchors.py --write-fixture",
            "observations": rows,
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        FIXTURE.write_text(text, encoding="utf-8")
        print(f"\nwrote {len(rows)} observations to {FIXTURE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
