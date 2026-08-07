#!/usr/bin/env python
"""Evaluate the comparison engine against the corpus — Stage 0e.

    services/backend/.venv/Scripts/python.exe tools/eval.py --method deterministic
    ... tools/eval.py --provenance mutation --json out.json
    ... tools/eval.py --explain M745200N01-rev-mut002

The run calls `generate_deterministic_candidates` directly — not the cache, which would
serve whatever the engine did last time — and asserts that no non-local socket is opened,
so "zero network calls" is enforced rather than claimed.

`--explain` prints every decision the scorer made on one pair. The staged plan requires two
pairs be audited that way before any aggregate is trusted: the scorer is itself a differ and
can be wrong in the same ways the engine can.
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

from services.backend.infrastructure.eval.corpus import (  # noqa: E402
    CorpusError,
    load_corpus,
)
from services.backend.infrastructure.eval.runner import (  # noqa: E402
    OFFLINE_METHODS,
    run_corpus,
)
from services.backend.infrastructure.eval.scorer import format_report  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    corpus = load_corpus(
        include_held_out=args.include_held_out,
        held_out_reason=args.reason,
    )
    if not corpus.pairs:
        print("No pairs in the corpus. Export some with tools/eval_corpus.py.")
        return 1

    result = await run_corpus(
        corpus,
        method=args.method,
        provenance=args.provenance,
        enforce_offline=not args.allow_network,
    )

    if args.explain:
        target = next(
            (p for p in result.score.pair_scores if p.pair_id == args.explain), None
        )
        if target is None:
            raise SystemExit(f"{args.explain!r} was not scored. Is it labelled?")
        print(target.explain())
        return 0

    print(format_report(result.score))
    print()
    print(
        f"  {result.pairs_run} pair(s) scored in {result.seconds:.2f}s, method={args.method}"
        + ("" if args.allow_network else ", zero non-local sockets (enforced)")
    )
    if result.skipped:
        print(f"  {len(result.skipped)} pair(s) skipped for having no ground truth:")
        for item in result.skipped[:10]:
            print(f"    {item}")

    if args.json:
        payload = result.score.to_dict()
        payload["seconds"] = round(result.seconds, 3)
        payload["method"] = args.method
        payload["skipped"] = result.skipped
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  wrote {args.json}")

    if args.baseline:
        from services.backend.infrastructure.audit.comparison.cache_manager import (
            ComparisonCacheManager,
        )

        # Deliberately omits wall-clock time and the pair list: a baseline is compared
        # against future runs, and a field that changes every run makes every diff noise.
        # Stamped with the cache version because that is what invalidates the comparison —
        # a baseline measured under v38 says nothing about v39's engine.
        payload = result.score.to_dict()
        payload["method"] = args.method
        payload["cache_version"] = ComparisonCacheManager.COMPARISON_CACHE_VERSION
        payload["scorer_note"] = (
            "Mutation pairs are drawn from the engine's own comparison pool, so they "
            "cannot reveal a scoping bug and their category attribution is not "
            "independent. Human pairs are required for both."
        )
        Path(args.baseline).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  wrote baseline {args.baseline} (cache {payload['cache_version']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    parser = argparse.ArgumentParser(prog="eval", description=__doc__)
    parser.add_argument(
        "--method",
        default="deterministic",
        help=f"comparison method. Offline-capable today: {sorted(OFFLINE_METHODS)}",
    )
    parser.add_argument(
        "--provenance",
        choices=["human", "mutation"],
        help="score only one kind of pair. Mutation-only numbers cannot settle category "
        "attribution or scoping — see the report footer.",
    )
    parser.add_argument("--json", help="write the full result to this path")
    parser.add_argument(
        "--baseline",
        help="write a stable, timing-free artifact stamped with the cache version, for "
        "committing and diffing against future runs",
    )
    parser.add_argument("--explain", help="print the scorer's decisions for one pair id")
    parser.add_argument("--include-held-out", action="store_true")
    parser.add_argument("--reason", default="", help="required with --include-held-out")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="disable the no-network guard. A number produced this way is not reproducible "
        "and must not be published as a baseline.",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_run(args))
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
