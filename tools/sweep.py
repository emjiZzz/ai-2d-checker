#!/usr/bin/env python
"""Measure which tuning constants affect anything — Stage 0.5b.

    services/backend/.venv/Scripts/python.exe tools/sweep.py
    ... tools/sweep.py --params changed_similarity_floor,min_fuzzy_length
    ... tools/sweep.py --include-zone --json sweep.json

**This is a sensitivity analysis, not a calibration.** The corpus is one drawing family of
synthetic edits, so a best value found here is the best value *for that sheet against the
mutator*. The report says so, and there is deliberately no flag that writes results back into
`DEFAULT_PARAMS`.

Zone constants are excluded unless `--include-zone`: they feed `safe_filter`, zone templates
and `views_exclusions()`, and users have hand-pinned templates that moving them can silently
invalidate. That pass needs a "pinned templates still resolve" assertion this does not perform.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.infrastructure.eval.corpus import CorpusError, load_corpus  # noqa: E402
from services.backend.infrastructure.eval.runner import no_network  # noqa: E402
from services.backend.infrastructure.eval.sweep import format_sweep, run_sweep  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    corpus = load_corpus()
    if not corpus.pairs:
        print("No pairs in the corpus. Export some with tools/eval_corpus.py.")
        return 1

    names = [n.strip() for n in args.params.split(",") if n.strip()] if args.params else None

    def progress(message: str) -> None:
        if args.verbose:
            print(f"  {message}", flush=True)

    with no_network():
        result = await run_sweep(
            corpus,
            names=names,
            include_zone=args.include_zone,
            progress=progress,
        )

    print(format_sweep(result))

    if args.json:
        payload = {
            "baseline_f1": result.baseline.f1,
            "baseline_exactness": result.baseline.exactness,
            "pairs": result.pairs,
            "seconds": round(result.seconds, 1),
            "note": (
                "SENSITIVITY, NOT CALIBRATION. One drawing family of synthetic edits. "
                "Best values here must not be written into DEFAULT_PARAMS."
            ),
            "parameters": [
                {
                    "name": s.name,
                    "default": s.default,
                    "values": s.values,
                    "f1": [m.f1 if m else None for m in s.scores],
                    "exactness": [m.exactness if m else None for m in s.scores],
                    "spread": round(s.spread, 4),
                    "f1_spread": round(s.f1_spread, 4),
                    "exactness_spread": round(s.exactness_spread, 4),
                    "flat": s.is_flat,
                }
                for s in result.sensitivities
            ],
        }
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n  wrote {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    parser = argparse.ArgumentParser(prog="sweep", description=__doc__)
    parser.add_argument("--params", default="", help="comma-separated subset to sweep")
    parser.add_argument(
        "--include-zone",
        action="store_true",
        help="also sweep zone constants — needs a pinned-template check this does not do",
    )
    parser.add_argument("--json", help="write the full result to this path")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_run(args))
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
