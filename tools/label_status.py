#!/usr/bin/env python
"""What the learned model will actually see the next time it trains — Stage 2/3.

    services/backend/.venv/Scripts/python.exe tools/label_status.py
    ... tools/label_status.py --json      # machine-readable, for a dashboard or a check

Reads the live `audit_feedback` collection and reports the corpus the way `trainer.build_bundle`
counts it, not the way a human would skim it. Three things it exists to make visible:

1. The class balance, not the row count. `MIN_TRAIN` is a floor, and crossing it is not the
same as being ready. `inference._decide` flips a deterministic `CHANGED/ADDED/REMOVED` to
`MATCHED` whenever the trained head returns `p_true < LOW_THRESH`, so a head trained on a corpus
that is mostly label 0 suppresses findings — the false-negative direction, in the system whose
headline gap is that false negatives have never been measured. A tool that printed only
"36 / 40" would actively encourage the cheapest and worst way to reach 40.

2. Which verbs train nothing. `MATCHER_FEEDBACK` and `value_correction` are captured and
deliberately unlabelled. They are real human judgments that move no model today, and if that
bucket is the largest one, the corpus is telling you where the defect is.

3. Which bundle is live. The `.meta.json` is the only figure in this project that changes
without a commit, so the ledger's copy of it goes stale silently. It did: it read 21 for weeks
while the corpus held 36.

The label sets and thresholds are imported from `trainer`/`config` rather than restated
here. That is deliberate and is the opposite of the convention in `tests/` — a test pins the
backend's wording literally so a change *fails*, but this tool must report what the trainer will
actually do, so it has to move when the trainer moves.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.config import settings  # noqa: E402
from services.backend.infrastructure.learning import config as learning_config  # noqa: E402
from services.backend.infrastructure.learning.model_holder import learned_model_dir  # noqa: E402
from services.backend.infrastructure.learning.trainer import (  # noqa: E402
    MATCHER_FEEDBACK,
    VERDICT_ONE,
    VERDICT_ZERO,
    majority_class_baseline,
)

# Above this share of label 0, a trained head's prior is negative enough that `p_true` clears
# LOW_THRESH on ordinary findings and the model starts suppressing rather than discriminating.
# Not a measured threshold — a stated convention, flagged as one, in the same spirit as
# `min_structured_value_length`. Replace it with a measured value once held-out pairs exist.
SKEW_WARN_SHARE = 0.65

# Below this much accuracy over the majority-class baseline, the head is barely doing more than
# predicting the common answer — which in SPATIAL_CATEGORIES is the suppressing answer. Also a
# stated convention, not a measured one; it mirrors the 0.15 lift gate `retrieval/metrics.py`
# applies to recall over its chance floor, which is the closest thing to a precedent here.
MIN_MEANINGFUL_LIFT = 0.15


def _bucket(verb: str | None) -> str:
    if verb in VERDICT_ZERO:
        return "verdict-0"
    if verb in VERDICT_ONE:
        return "verdict-1"
    if verb in MATCHER_FEEDBACK:
        return "matcher (parked)"
    return "no verdict label"


def _live_bundle_meta() -> dict[str, Any] | None:
    """The meta beside the bundle the app actually loads — env, then storage, then vault."""
    try:
        meta = learned_model_dir() / learning_config.META_FILENAME
        if meta.is_file():
            return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


async def collect() -> dict[str, Any]:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=4000)
    try:
        db = client[settings.MONGO_DB_NAME]
        docs = await db["audit_feedback"].find({}).to_list(length=None)

        # `build_bundle` skips retracted rows entirely — not even counted in n_total — so a
        # report that included them would overstate the corpus against the trainer's own view.
        live = [d for d in docs if not d.get("retracted_at")]
        verbs = Counter(d.get("human_corrected_status") for d in live)

        zeros = sum(n for v, n in verbs.items() if v in VERDICT_ZERO)
        ones = sum(n for v, n in verbs.items() if v in VERDICT_ONE)
        parked = sum(n for v, n in verbs.items() if v in MATCHER_FEEDBACK)
        total = zeros + ones

        violations_total = await db["audit_violations"].count_documents({})
        violations_unreviewed = await db["audit_violations"].count_documents(
            {"resolution_type": None}
        )
    finally:
        client.close()

    return {
        "rows_total": len(docs),
        "rows_live": len(live),
        "rows_retracted": len(docs) - len(live),
        "verbs": {str(v): n for v, n in verbs.most_common()},
        "verdict_labels": total,
        "class_0": zeros,
        "class_1": ones,
        "min_train": learning_config.MIN_TRAIN,
        "short_by": max(0, learning_config.MIN_TRAIN - total),
        "both_classes_present": zeros > 0 and ones > 0,
        "matcher_parked": parked,
        "violations_total": violations_total,
        "violations_unreviewed": violations_unreviewed,
        "low_thresh": learning_config.LOW_THRESH,
        "high_thresh": learning_config.HIGH_THRESH,
        "spatial_categories": list(learning_config.SPATIAL_CATEGORIES),
        "live_bundle": _live_bundle_meta(),
    }


def render(s: dict[str, Any]) -> None:
    # ASCII only in everything below. This function crashed with UnicodeEncodeError on the default
    # Windows cp932 console — U+2014 EM DASH is not in cp932 — which took out the *whole* report,
    # including the class-balance warning, on the platform this ships to. See
    # `Gotcha - Our Own Punctuation Broke on the cp932 Console`: keep the punctuation we add to
    # ASCII; drawing text is data and stays exempt. The docstrings above may keep their em dashes,
    # since nothing encodes them to a terminal.
    print("Learned model - what the next training run will see\n")
    print(f"  audit_feedback rows   {s['rows_total']}")
    print(f"    live                {s['rows_live']}")
    print(f"    retracted           {s['rows_retracted']}   (never train)")

    print("\n  verbs (live rows)")
    for verb, n in s["verbs"].items():
        print(f"    {verb:32} {n:5}   {_bucket(verb)}")

    total = s["verdict_labels"]
    zeros, ones = s["class_0"], s["class_1"]
    print(f"\n  verdict labels        {total} / {s['min_train']}", end="")
    print(f"   (short by {s['short_by']})" if s["short_by"] else "   - threshold met")
    print(f"    class 0             {zeros}")
    print(f"    class 1             {ones}")
    print(f"    both classes        {'yes' if s['both_classes_present'] else 'NO - will not train'}")

    share = zeros / total if total else 0.0
    baseline = majority_class_baseline({"0": zeros, "1": ones})
    print(f"\n  negative share        {share:.0%}")
    if baseline is not None:
        print(
            f"  majority baseline     {baseline:.1%}   "
            f"<- always answering '{'class 0' if zeros >= ones else 'class 1'}' scores this"
        )
    if share > SKEW_WARN_SHARE:
        print(
            f"    ** SKEWED. At this balance a trained head clears LOW_THRESH "
            f"({s['low_thresh']}) on ordinary findings and flips\n"
            f"       CHANGED/ADDED/REMOVED -> MATCHED in "
            f"{', '.join(s['spatial_categories'])}.\n"
            f"       Prefer class-1 corrections (confirmed_valid, verdict_changed) - "
            f"honestly earned, not farmed."
        )

    if s["matcher_parked"]:
        print(
            f"\n  matcher feedback      {s['matcher_parked']}   parked for Stage 3 - "
            f"trains nothing today"
        )
        if s["matcher_parked"] >= max(1, s["short_by"]):
            print(
                "    ** The matcher has more data waiting than the verdict head is short. "
                "That is a\n       statement about where the defect is."
            )

    print(
        f"\n  audit_violations      {s['violations_total']} total, "
        f"{s['violations_unreviewed']} with no supervisor verdict"
    )

    meta = s["live_bundle"]
    if meta:
        print(
            f"\n  live bundle           trained {meta.get('trained_at')}\n"
            f"    n_verdict {meta.get('n_verdict')}   n_category {meta.get('n_category')}   "
            f"metrics {meta.get('metrics') if meta.get('metrics') else '{} (inert)'}"
        )
        # The accuracy is never shown alone. On this corpus a bare 0.733 reads as strong and is
        # ten points over always-guessing, not seventy-three. Same rule `retrieval/metrics.py`
        # enforces for recall against `chance_recall_at_k`.
        bundle_metrics = meta.get("metrics") or {}
        cv = bundle_metrics.get("verdict_cv_accuracy")
        floor = bundle_metrics.get("verdict_majority_baseline")
        if isinstance(cv, (int, float)):
            if isinstance(floor, (int, float)):
                lift = cv - floor
                print(
                    f"    cv accuracy {cv:.1%} against a {floor:.1%} majority baseline "
                    f"= {lift:+.1%} of skill"
                )
                if lift < MIN_MEANINGFUL_LIFT:
                    print(
                        "    ** That lift is small. The head is close to just predicting the\n"
                        "       majority class, which in SPATIAL_CATEGORIES means suppressing."
                    )
            else:
                print(
                    f"    cv accuracy {cv:.1%} - baseline not recorded (bundle predates it); "
                    "retrain to get it"
                )

        stale = meta.get("n_verdict") != total
        if stale:
            print(
                f"    ** bundle is behind the corpus ({meta.get('n_verdict')} vs {total}) - "
                "it retrains on the next correction."
            )
    else:
        print("\n  live bundle           none found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="emit raw JSON instead of a report")
    args = parser.parse_args()

    try:
        snapshot = asyncio.run(collect())
    except Exception as err:
        print(f"[fail] could not read {settings.MONGO_DB_NAME}: {err}", file=sys.stderr)
        print("       Is MongoDB running? This tool reads the live corpus.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        render(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
