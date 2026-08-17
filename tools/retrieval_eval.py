"""Measure retrieval against hand-labelled queries — Stage R2.

    python tools/retrieval_eval.py census
    python tools/retrieval_eval.py score --collection standards
    python tools/retrieval_eval.py worksheet --collection standards --out drafts/
    python tools/retrieval_eval.py score --collection standards --baseline

`census` answers the question that has to come first: how many documents are actually in each
collection. A recall figure over an empty or tiny corpus is arithmetic, not evidence, and this
system's corpus turned out to be exactly that case.

`worksheet` generates a markdown draft for a human to fill in. It deliberately does **not**
generate labels — it retrieves candidates and leaves the relevance judgement blank, because a
label a script wrote is not evidence about whether retrieval helps a person. See `labels.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.infrastructure import retrieval  # noqa: E402
from services.backend.infrastructure.retrieval.evaluate import (  # noqa: E402
    ALL_COLLECTIONS,
    census_all,
    evaluate,
    format_census,
)
from services.backend.infrastructure.retrieval.labels import (  # noqa: E402
    GUIDELINE_VERSION,
    LabelError,
    LabelSet,
    default_baseline_path,
    default_labels_path,
)
from services.backend.infrastructure.retrieval.metrics import format_report  # noqa: E402

#: Collections whose contents are client-specific and gitignored. Their record counts and
#: digests are machine-local, so a committed baseline must not pin them — otherwise the fixture
#: only matches the machine that generated it, and every other install reads a normal difference
#: as a regression.
CLIENT_LOCAL_COLLECTIONS = frozenset({retrieval.DOMAIN_RULES})


def _census_entry(entry) -> dict:
    if entry.collection in CLIENT_LOCAL_COLLECTIONS:
        return {
            "collection": entry.collection,
            "client_local": True,
            "note": (
                "Sourced from the gitignored client rules directory, so record count, digest "
                "and encoder state vary per install. Deliberately not pinned: a committed "
                "value here would match one machine and read as a regression everywhere else."
            ),
        }
    return {
        "collection": entry.collection,
        "client_local": False,
        "status": str(entry.status),
        "n_records": entry.n_records,
        "encoder": entry.encoder,
        "source_digest": entry.source_digest,
    }


def cmd_census(args: argparse.Namespace) -> int:
    entries = census_all()
    print(format_census(entries))

    if args.baseline:
        # A census baseline is what gets committed while no human labels exist. It pins the
        # *reason* there is no metric, so the day a standard is uploaded the diff is visible
        # and nobody has to re-derive why retrieval was never measured.
        payload = {
            "status": "no-measurement",
            "reason": (
                "No human-labelled queries exist for any collection, and two of three "
                "collections hold zero documents. recall@5 cannot be computed, and computing "
                "it over the third (6 records, k=5) would report a chance score of 0.83 as if "
                "it were a result."
            ),
            "guideline_version": GUIDELINE_VERSION,
            "collections": [_census_entry(e) for e in entries],
        }
        path = default_baseline_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\n  wrote census baseline {path.relative_to(REPO_ROOT)}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    labels_path = Path(args.labels) if args.labels else default_labels_path(args.collection)

    try:
        label_set = LabelSet.load(labels_path)
    except LabelError as err:
        print(f"  Cannot score: {err}")
        print(f"\n  Create labels with:  python tools/retrieval_eval.py worksheet "
              f"--collection {args.collection}")
        return 1

    result = evaluate(
        label_set,
        collection=args.collection,
        k=args.k,
        include_synthetic=args.include_synthetic,
    )

    print(format_census([result.census]))
    print(format_report(result.score, args.collection, result.census.encoder or "none"))

    if args.baseline:
        if args.include_synthetic:
            print("\n  REFUSED: a baseline may not include synthetic labels. They measure "
                  "whether the\n  index can find text copied out of itself, and publishing that "
                  "as a baseline is\n  exactly how a meaningless number becomes a reference "
                  "point.")
            return 2
        path = default_baseline_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\n  wrote baseline {path.relative_to(REPO_ROOT)}")

    return 0


def cmd_worksheet(args: argparse.Namespace) -> int:
    """Emit a markdown worksheet of candidates for a human to judge."""
    out_dir = Path(args.out) if args.out else REPO_ROOT / "storage" / "retrieval" / "drafts"
    out_dir.mkdir(parents=True, exist_ok=True)

    queries = [q.strip() for q in (args.queries or "").split(";") if q.strip()]
    if not queries:
        print("  No queries given. Pass --queries 'first query; second query; ...'")
        print("  Queries must come from real audit situations, not from the corpus text -")
        print("  a query written by reading the answer measures nothing.")
        return 1

    lines = [
        f"# Retrieval labelling worksheet - `{args.collection}`",
        "",
        f"Guideline version: `{GUIDELINE_VERSION}`",
        "",
        "**Relevance test:** would a checker auditing a drawing that raised this query want this",
        "clause shown to them? Judge each (query, chunk) pair on its own. Mark `[x]` for relevant.",
        "",
        "If *nothing* retrieved is relevant, write the query under `## Unanswerable` at the",
        "bottom instead of leaving every box unticked — 'the corpus cannot answer this' is a",
        "coverage finding worth recording, and is not the same as 'the encoder ranked badly'.",
        "",
        "---",
        "",
    ]

    for i, text in enumerate(queries, start=1):
        outcome = retrieval.query(text, collection=args.collection, top_k=args.k)
        lines += [f"## Q{i}. {text}", ""]
        if not outcome.answered:
            lines += [f"> Index unusable: {outcome.status} - {outcome.detail}", ""]
            continue
        if not outcome.hits:
            lines += ["> Nothing retrieved. Record under Unanswerable.", ""]
            continue
        for hit in outcome.hits:
            snippet = hit.record.text.replace("\n", " ")[:160]
            lines += [
                f"- [ ] `{hit.record.id}`  (score {hit.score:.3f})  **{hit.record.citation()}**",
                f"      {snippet}",
            ]
        lines.append("")

    lines += ["---", "", "## Unanswerable", "", "- ", ""]

    path = out_dir / f"labels-{args.collection}-worksheet.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote {path}")
    print(f"  {len(queries)} query/queries. Fill it in, then transcribe to "
          f"{default_labels_path(args.collection).relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    # Same guard every other console tool here carries. Without it this script died with
    # UnicodeEncodeError on a cp932 console while printing the `worksheet` usage hint -- so the
    # one command that explains how to unblock the retrieval metric was the one that crashed.
    # See [[Gotcha - Our Own Punctuation Broke on the cp932 Console]].
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    parser = argparse.ArgumentParser(
        prog="retrieval_eval",
        description="Measure retrieval against hand-labelled queries (Stage R2).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cen = sub.add_parser("census", help="report how many documents each collection holds")
    cen.add_argument(
        "--baseline",
        action="store_true",
        help="commit the census as the retrieval baseline (used while no labels exist)",
    )

    score = sub.add_parser("score", help="score a label set against the live index")
    score.add_argument("--collection", default=retrieval.STANDARDS, choices=ALL_COLLECTIONS)
    score.add_argument("--labels", help="path to a label set (default: the committed fixture)")
    score.add_argument("--k", type=int, default=5)
    score.add_argument(
        "--include-synthetic",
        action="store_true",
        help="include generated labels. A smoke test only — never a baseline.",
    )
    score.add_argument(
        "--baseline",
        action="store_true",
        help="write the result to tests/fixtures/retrieval/retrieval-baseline.json",
    )

    work = sub.add_parser("worksheet", help="emit a markdown worksheet for a human to label")
    work.add_argument("--collection", default=retrieval.STANDARDS, choices=ALL_COLLECTIONS)
    work.add_argument("--queries", help="semicolon-separated real queries")
    work.add_argument("--k", type=int, default=10)
    work.add_argument("--out", help="output directory")

    args = parser.parse_args()
    commands = {"census": cmd_census, "score": cmd_score, "worksheet": cmd_worksheet}
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
