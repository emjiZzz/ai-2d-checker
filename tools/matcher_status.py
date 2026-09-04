#!/usr/bin/env python
"""What the parked matcher feedback says about the matcher — Step 1 of the matcher plan.

    services/backend/.venv/Scripts/python.exe tools/matcher_status.py
    ... tools/matcher_status.py --json      # machine-readable

See `docs/vault/01 - Architecture/Matcher Feedback - Making the Parked Corpus Count.md`.

## Why this exists

`trainer.MATCHER_FEEDBACK` captures `mispaired_missing_counterpart` and `mispaired_wrong_match`
and maps neither to a verdict label. The restraint is correct -- label 0 would suppress a finding
that may be genuine, label 1 would affirm a pairing the human just rejected -- but the effect is
that the single loudest signal in the corpus is read by nothing.

Those rows are negative-only (measured 2026-08-19: 3 of 106 carry the correct counterpart),
so they cannot train a matcher even once Stage 3 exists. They CAN measure one. This reports what
they say, which needs no model, no schema change and no new labelling.

## What it deliberately does NOT report

A rate. `audit_feedback` records rejections, never the total pairings attempted, so there is
no denominator anywhere in this collection. "46 rejections in drawing_views/dimensions" is a
fact; "X% of pairings are wrong" would require a number this data does not contain, and
inventing it would be the kind of plausible-looking figure this project exists to avoid.

Read-only. Opens no writes and takes no locks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.config import settings  # noqa: E402
from services.backend.infrastructure.learning.trainer import MATCHER_FEEDBACK  # noqa: E402

FEEDBACK = "audit_feedback"


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the matcher-feedback rows. Pure, so the counting is testable offline.

    `rows` is every `audit_feedback` document; the filtering to matcher verbs happens here rather
    than in the query so that the "of N total" denominators are real.
    """
    live = [r for r in rows if not r.get("retracted_at")]
    matcher = [r for r in live if r.get("human_corrected_status") in MATCHER_FEEDBACK]

    by_verb: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_feature: Counter[str] = Counter()
    by_pair: Counter[tuple[str, str]] = Counter()
    with_counterpart = 0
    with_both_coords = 0

    for r in matcher:
        snap = r.get("finding_snapshot") or {}
        by_verb[str(r.get("human_corrected_status"))] += 1
        category = str(snap.get("category") or r.get("category") or "unknown")
        feature = str(snap.get("feature") or "unclassified")
        by_category[category] += 1
        by_feature[feature] += 1
        by_pair[(category, feature)] += 1
        # The correct counterpart, when the engineer typed one. This is the trainable subset,
        # and it is the number that decides whether Stage 3 has anything to learn from.
        if str(r.get("human_comment") or "").strip():
            with_counterpart += 1
        if snap.get("ref_coord") and snap.get("rev_coord"):
            with_both_coords += 1

    return {
        "rows_total": len(rows),
        "rows_live": len(live),
        "matcher_rows": len(matcher),
        "by_verb": dict(by_verb.most_common()),
        "by_category": dict(by_category.most_common()),
        "by_feature": dict(by_feature.most_common()),
        "top_category_feature": [
            {"category": c, "feature": f, "count": n} for (c, f), n in by_pair.most_common(8)
        ],
        "with_counterpart": with_counterpart,
        "with_both_coords": with_both_coords,
    }


def render(s: dict[str, Any]) -> str:
    total = s["matcher_rows"]
    if not total:
        return "No matcher feedback recorded. Nothing to report."

    out: list[str] = []
    pct = lambda n: f"{n / total:4.0%}"  # noqa: E731 — one local formatter, used six times

    out.append(f"Matcher feedback — {total} live row(s) of {s['rows_live']} live corrections\n")
    out.append("  what the engineer said")
    for verb, n in s["by_verb"].items():
        # The verbs are not two flavours of one complaint. `missing_counterpart` is a pairing
        # RECALL failure (no candidate was offered); `wrong_match` is a discrimination failure
        # (the wrong candidate won). A model helps with the second and not the first.
        kind = "recall: nothing was paired" if verb.endswith("missing_counterpart") else "discrimination: wrong pair won"
        out.append(f"    {n:>4}  {pct(n)}  {verb:<32} {kind}")

    out.append("\n  by category")
    for k, n in s["by_category"].items():
        out.append(f"    {n:>4}  {pct(n)}  {k}")

    out.append("\n  by feature")
    for k, n in list(s["by_feature"].items())[:8]:
        out.append(f"    {n:>4}  {pct(n)}  {k}")

    out.append("\n  concentration (category / feature)")
    for row in s["top_category_feature"]:
        out.append(f"    {row['count']:>4}  {pct(row['count'])}  {row['category']} / {row['feature']}")

    top = s["top_category_feature"][0] if s["top_category_feature"] else None
    if top and top["count"] / total >= 0.30:
        out.append(
            f"\n  ** {pct(top['count'])} of every rejection is {top['category']} / {top['feature']}."
        )
        out.append("     A defect that concentrated would be a threshold or a scoping rule before")
        out.append("     it is a missing model. Investigate the rule before building a matcher.")

    out.append(f"\n  trainable subset      {s['with_counterpart']} / {total}   carry the correct counterpart")
    if s["with_counterpart"] < total:
        out.append("     The rest record a rejection with no correction. A matcher cannot be")
        out.append("     trained on negatives alone — there is no target to learn toward. Step 2")
        out.append("     of the plan changes what is captured; it cannot recover these.")
    out.append(f"  both coordinates      {s['with_both_coords']} / {total}   (a distance is derivable)")
    return "\n".join(out)


async def collect() -> dict[str, Any]:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=8000)
    try:
        db = client[settings.MONGO_DB_NAME]
        rows = await db[FEEDBACK].find({}).to_list(length=None)
    finally:
        client.close()
    return summarise(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    try:
        summary = asyncio.run(collect())
    except Exception as err:  # noqa: BLE001 — a read-only report should not traceback
        print(f"[fail] could not read {settings.MONGO_DB_NAME}: {err}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
