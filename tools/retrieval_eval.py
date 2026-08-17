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
    synthetic_label_set,
)
from services.backend.infrastructure.retrieval.metrics import (  # noqa: E402
    MIN_QUERIES_FOR_VERDICT,
    format_report,
)
from services.backend.infrastructure.retrieval.queries import (  # noqa: E402
    QueryOrigin,
    QuerySet,
    build_drawing_query,
    default_queries_path,
    layer_names_for,
)

#: Collections whose contents are client-specific and gitignored. Their record counts and
#: digests are machine-local, so a committed baseline must not pin them — otherwise the fixture
#: only matches the machine that generated it, and every other install reads a normal difference
#: as a regression.
#: `vault` is deliberately absent: it is git-tracked and identical on every install at a given
#: commit, so a committed value here is valid rather than machine-specific. It does churn with
#: ordinary documentation work, which is a baseline-regeneration nuisance and *not* the property
#: this set is about.
CLIENT_LOCAL_COLLECTIONS = frozenset(
    {
        retrieval.DOMAIN_RULES,
        retrieval.CORRECTIONS,
        retrieval.FINDINGS,
        retrieval.ENTITIES,
    }
)


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


def _harvest_production_queries(collection: str) -> int:
    """Record the query the pipeline builds for every drawing in the database.

    These are real in the sense the guideline cares about — they are literally what production
    searches with, and they are built from drawing metadata rather than from the corpus text, so
    they do not smuggle the answer into the question.

    They are *not* a substitute for questions a checker asked. Every one has the same shape, so
    a set made only of these measures the production path rather than a checker's need. The
    report below says so rather than leaving it to be inferred from the origin column.
    """
    # Deferred on purpose: these pull in motor and beanie, and `census`, `score` and
    # `worksheet` all run without a database. Importing at module level would make every
    # invocation of this tool pay for a driver only `harvest` uses.
    import asyncio  # noqa: PLC0415

    from services.backend.domain.models.drawing_document import (  # noqa: PLC0415
        DrawingDocument,
    )
    from services.backend.infrastructure.database.connection import (  # noqa: PLC0415
        db_manager,
    )

    async def run() -> int:
        if not await db_manager.connect():
            print("  Could not connect to MongoDB; no drawings to harvest from.")
            return 1

        drawings = await DrawingDocument.find_all().to_list()
        path = default_queries_path(collection)
        store = QuerySet.load(path, collection)

        # A production query is *derived* from the current code and the current drawings, so a
        # harvest is a projection and must be idempotent. Re-running after the query
        # construction changes would otherwise leave the store holding queries production can
        # no longer issue, alongside the new ones, with nothing to tell them apart.
        # Human-origin queries are never touched: those are the input that cannot be regenerated.
        dropped = store.drop_origin(QueryOrigin.PRODUCTION)

        added = skipped = no_keywords = 0
        for drawing in drawings:
            layer_names = await layer_names_for(str(drawing.id))
            text = build_drawing_query(drawing, layer_names)
            if text is None:
                no_keywords += 1
                continue
            entry = store.add(
                text,
                QueryOrigin.PRODUCTION,
                note=f"pipeline query for {drawing.file_name}",
            )
            if entry is None:
                skipped += 1
            else:
                added += 1

        store.save(path)
        await db_manager.disconnect()

        print(f"  {len(drawings)} drawing(s) examined")
        print(f"  replaced {dropped} stale production query/queries (human-origin kept)")
        print(f"  added   {added}")
        print(f"  skipped {skipped} (query text already stored)")
        print(f"  no keywords {no_keywords}")
        print(f"  wrote {path}")
        return 0

    return asyncio.run(run())


def cmd_smoke(args: argparse.Namespace) -> int:
    """Score a generated label set to prove the measurement path works. Never evidence.

    Stage C asks an annotator for ~30 relevance judgements per collection. This runs the whole
    scoring path first — index load, encoder, ranking, gate arithmetic, report — on labels
    generated from the corpus, so a defect anywhere in it surfaces before the hours are spent
    rather than after.

    The result is circular by construction and the report says so. What is worth reading is not
    the recall figure but **which gates fire**: a collection that cannot clear the chance floor
    today will not clear it with real labels either, and that is knowable now.
    """
    label_set = synthetic_label_set(args.collection, limit=args.limit)
    if not label_set.labels:
        print(f"  '{args.collection}' has no headed records to generate from.")
        print("  Collections built from Mongo documents carry no section headings; this smoke")
        print("  test only applies to the markdown-chunked ones (vault, domain_rules).")
        return 1

    result = evaluate(
        collection=args.collection,
        label_set=label_set,
        k=args.k,
        include_synthetic=True,
    )
    print(format_report(result.score, args.collection, result.census.encoder))
    print(
        "\n  ** SMOKE TEST. These labels were generated from the corpus, so the recall figure\n"
        "     is circular and is not a measurement of anything. Read the gate lines instead:\n"
        "     they are the real constraint on whether this collection can be measured at all."
    )
    return 0


def cmd_queries(args: argparse.Namespace) -> int:
    """The Stage B query store."""
    collection = args.collection
    path = default_queries_path(collection)

    if args.subcommand == "harvest":
        return _harvest_production_queries(collection)

    store = QuerySet.load(path, collection)

    if args.subcommand == "add":
        origin = QueryOrigin(args.origin)
        entry = store.add(args.query, origin, note=args.note)
        if entry is None:
            print(f"  Already stored; nothing written. ({args.query})")
            return 0
        store.save(path)
        print(f"  added {entry.query_id} [{entry.origin}] {entry.query}")
        print(f"  wrote {path}")
        return 0

    # list
    counts = store.counts_by_origin()
    print(f"\n  QUERY STORE - '{collection}'  ({path})")
    print("  " + "-" * 74)
    if not store.queries:
        print("  empty. Queries must come from real audit situations, never from the corpus.")
        print("  `queries harvest` records what the pipeline itself searches with;")
        print("  `queries add --query '...'` records a question a person actually asked.")
        return 0

    for q in store.queries:
        print(f"  {q.query_id}  [{q.origin:10}]  {q.query[:80]}")
    print("  " + "-" * 74)
    print(f"  {len(store.queries)} stored: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

    human = len(store.queries) - counts.get(str(QueryOrigin.PRODUCTION), 0)
    print(f"  {MIN_QUERIES_FOR_VERDICT} needed for a verdict.")
    if human == 0 and store.queries:
        print(
            "  ** ALL PRODUCTION-SHAPED. These measure the production path, not a checker's\n"
            "     need - every one has the same form. Add checker-asked questions before\n"
            "     treating a score over this set as evidence about retrieval quality."
        )
    return 0


def cmd_worksheet(args: argparse.Namespace) -> int:
    """Emit a markdown worksheet of candidates for a human to judge."""
    out_dir = Path(args.out) if args.out else REPO_ROOT / "storage" / "retrieval" / "drafts"
    out_dir.mkdir(parents=True, exist_ok=True)

    if getattr(args, "from_store", False):
        store = QuerySet.load(default_queries_path(args.collection), args.collection)
        queries = [q.query for q in store.queries]
        if not queries:
            print(f"  The query store for '{args.collection}' is empty.")
            print("  Run `retrieval_eval.py queries harvest` or `queries add` first.")
            return 1
    else:
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
    work.add_argument(
        "--from-store",
        action="store_true",
        help="take the queries from the Stage B query store instead of --queries",
    )
    work.add_argument("--k", type=int, default=10)
    work.add_argument("--out", help="output directory")

    q = sub.add_parser("queries", help="the Stage B query store (queries do not expire)")
    q_sub = q.add_subparsers(dest="subcommand", required=True)

    q_list = q_sub.add_parser("list", help="show the stored queries and their origins")
    q_list.add_argument("--collection", default=retrieval.STANDARDS, choices=ALL_COLLECTIONS)

    q_add = q_sub.add_parser("add", help="record one real query a person asked")
    q_add.add_argument("--collection", default=retrieval.STANDARDS, choices=ALL_COLLECTIONS)
    q_add.add_argument("--query", required=True, help="the question, in the words it was asked")
    q_add.add_argument(
        "--origin",
        default=str(QueryOrigin.CHECKER),
        choices=[str(o) for o in QueryOrigin],
        help="where it came from. 'production' is reserved for `harvest`.",
    )
    q_add.add_argument("--note", default="", help="the situation that raised it")

    q_harvest = q_sub.add_parser(
        "harvest",
        help="record the query the audit pipeline itself builds, for every drawing",
    )
    q_harvest.add_argument("--collection", default=retrieval.STANDARDS, choices=ALL_COLLECTIONS)

    smoke = sub.add_parser(
        "smoke",
        help="score generated labels to prove the path works. Circular; never evidence.",
    )
    smoke.add_argument("--collection", default=retrieval.VAULT, choices=ALL_COLLECTIONS)
    smoke.add_argument("--k", type=int, default=5)
    smoke.add_argument("--limit", type=int, default=None, help="cap the generated labels")

    args = parser.parse_args()
    commands = {
        "census": cmd_census,
        "score": cmd_score,
        "worksheet": cmd_worksheet,
        "queries": cmd_queries,
        "smoke": cmd_smoke,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
