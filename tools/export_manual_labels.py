#!/usr/bin/env python
"""Turn a manual engineer check into an eval-corpus label draft - the missing bridge.

    services/backend/.venv/Scripts/python.exe tools/export_manual_labels.py --pair-id M7452A1N01
    ... tools/export_manual_labels.py --pair-id M7452A1N01 --write
    ... tools/export_manual_labels.py --session 6a83aeab... --write

Then install it with the existing validator, which is the only thing that may write labels:

    ... tools/eval_corpus.py label --pair-id M7452A1N01 \\
        --from storage/eval/worksheets/M7452A1N01.labels.draft.json

## Why this exists

The desktop app records manual checks into Mongo (`ground_truth_markings`, addressed by DXF
handle). `eval_corpus.py` counts a pair as labelled only once a `PairLabels` document is
installed into `storage/eval/manifest.json`. NOTHING connected the two, so an engineer could
label every pair in the UI and `eval_corpus status` would never move off `4 / 8` -- the number
the whole maturity ladder gates on. The work existed and did not count.

## The two vocabularies do not line up, and this reports where

* The corpus's `VALID_STATUSES` is `{CHANGED, ADDED, REMOVED}`. A manual check also produces
  `MATCHED` and `NOT_A_FINDING`, which are not findings. They are exported as `not_findings`
  -- the guideline's "deliberately not labelled, and why" -- so a later false positive on one
  is attributable to a decision rather than to an oversight.
* A finding must carry an ADDRESS: a DXF handle (`REV-1B2A`) or a payload line index
  (`REF#412`). The app records handles; block-exploded content has none, and that is the normal
  case on a reference sheet (0.8-13% handle coverage measured over three pairs). Where the
  handle is missing this resolves the payload index instead, by UNIQUE text match against the
  exported entities. Non-unique or absent means the finding is reported as unexportable rather
  than guessed at -- a mis-addressed label is worse than a missing one, because it scores.

Read-only against Mongo and, without `--write`, against the disk too.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
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
from services.backend.infrastructure.eval.corpus import (  # noqa: E402
    GUIDELINE_VERSION,
    VALID_STATUSES,
    default_payload_dir,
    read_manifest,
)

SESSIONS = "manual_check_sessions"
MARKINGS = "ground_truth_markings"
DRAWINGS = "drawing_documents"

#: Statuses that are a decision NOT to flag, with the reason recorded on the label.
#: `MATCHED` is an assertion that the two sides agree; `NOT_A_FINDING` that a difference exists
#: and does not matter. Both are useful to the scorer for the same purpose and for different
#: reasons, so the reason string keeps them apart.
NON_FINDING_REASONS = {
    "MATCHED": "engineer recorded both sides as equivalent",
    "NOT_A_FINDING": "engineer recorded a difference that is deliberately not a finding",
}


async def _connect():
    """Primary URI, then the local fallback - the same two candidates the app tries."""
    from motor.motor_asyncio import AsyncIOMotorClient

    candidates = [settings.MONGO_URI]
    fallback = getattr(settings, "MONGO_FALLBACK_URI", "mongodb://127.0.0.1:27017")
    if fallback and fallback.strip() != settings.MONGO_URI.strip():
        candidates.append(fallback)
    last: Exception | None = None
    for uri in candidates:
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=4000)
        try:
            await client.admin.command("ping")
            return client
        except Exception as err:  # noqa: BLE001
            last = err
            client.close()
    raise SystemExit(f"no reachable MongoDB in {candidates}: {last}")


def _payload_index(entities: list[dict[str, Any]], text: str) -> int | None:
    """The line index of the ONE entity carrying this text, or None.

    Unique-or-nothing on purpose. A finding addressed to the wrong line still scores -- it just
    scores against an entity nobody looked at -- so an ambiguous match has to be a refusal. The
    comparison is on the raw recorded text because that is what the app stored verbatim; it is
    deliberately not normalised, since two entities that normalise alike are exactly the pair
    this must not choose between.
    """
    wanted = (text or "").strip()
    if not wanted:
        return None
    hits = [
        i
        for i, e in enumerate(entities)
        if str((e.get("properties") or {}).get("text") or "").strip() == wanted
        or str((e.get("geometry") or {}).get("text") or "").strip() == wanted
    ]
    return hits[0] if len(hits) == 1 else None


def _address(marking: dict[str, Any], side: str, entities: list[dict[str, Any]]) -> str | None:
    """`REF-1B2A` / `REV#412`, or None when the entity cannot be addressed at all."""
    handle = marking.get(f"{side.lower()}_handle")
    if handle:
        return f"{side}-{handle}"
    text = marking.get("ref_text" if side == "REF" else "rev_text")
    idx = _payload_index(entities, str(text or ""))
    return f"{side}#{idx}" if idx is not None else None


def _read_entities(pair_dir: Path, side: str) -> list[dict[str, Any]]:
    path = pair_dir / f"{side}.entities.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} does not exist - export the pair first.")
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_draft(
    markings: list[dict[str, Any]],
    *,
    pair_id: str,
    annotator: str,
    ref_entities: list[dict[str, Any]],
    rev_entities: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """The draft document, plus one line per marking that could not be exported.

    Pure, so the mapping is testable without a database or a corpus on disk.
    """
    findings: list[dict[str, Any]] = []
    not_findings: list[dict[str, Any]] = []
    skipped: list[str] = []

    for m in markings:
        if m.get("retracted_at"):
            continue
        status = str(m.get("status") or "").upper()
        # A REMOVED exists only on the reference; everything else anchors on the revision. Same
        # rule as `ExpectedFinding.default_side`, restated here because this has to pick the
        # handle BEFORE the label exists to ask.
        side = "REF" if status == "REMOVED" else "REV"
        entities = ref_entities if side == "REF" else rev_entities
        address = _address(m, side, entities)
        label = str(m.get("rev_text") or m.get("ref_text") or "<no text>")[:40]

        if address is None:
            skipped.append(f"{status:<13} {label}  (no {side} handle, and no unique text match)")
            continue

        if status in NON_FINDING_REASONS:
            not_findings.append(
                {"entity_handle": address, "reason": NON_FINDING_REASONS[status]}
            )
            continue

        if status not in VALID_STATUSES:
            skipped.append(f"{status:<13} {label}  (status has no corpus equivalent)")
            continue

        findings.append(
            {
                "entity_handle": address,
                "category": str(m.get("category") or ""),
                "status": status,
                "ref_text": str(m.get("ref_text") or ""),
                "rev_text": str(m.get("rev_text") or ""),
                "notes": str(m.get("notes") or ""),
                "is_bulk": bool(m.get("is_bulk")),
            }
        )

    draft = {
        "pair_id": pair_id,
        "guideline_version": GUIDELINE_VERSION,
        "annotator": annotator,
        "annotated_at": datetime.now(UTC).date().isoformat(),
        "notes": "Exported from a manual engineer check session by tools/export_manual_labels.py.",
        "findings": findings,
        "not_findings": not_findings,
    }
    return draft, skipped


async def run(args: argparse.Namespace) -> int:
    manifest = read_manifest()
    pairs = {p.get("pair_id"): p for p in manifest.get("pairs") or []}

    client = await _connect()
    try:
        db = client[settings.MONGO_DB_NAME]

        # Resolve the session either directly or through the pair's drawing FILE NAMES, which
        # are what the corpus and the app have in common - the corpus records a file name per
        # side, the app records a drawing id, and nothing else joins them.
        if args.session:
            from bson import ObjectId

            session = await db[SESSIONS].find_one({"_id": ObjectId(args.session)})
            if not session:
                raise SystemExit(f"no session {args.session}")
            pair_id = args.pair_id or ""
        else:
            entry = pairs.get(args.pair_id)
            if not entry:
                raise SystemExit(
                    f"no pair {args.pair_id!r} in the manifest - export it first with "
                    f"`tools/eval_corpus.py export`."
                )
            wanted = {entry["ref"]["file_name"], entry["rev"]["file_name"]}
            session = None
            for s in await db[SESSIONS].find({}).sort("started_at", -1).to_list(None):
                names = set()
                for key in ("ref_drawing_id", "rev_drawing_id"):
                    from bson import ObjectId

                    d = await db[DRAWINGS].find_one({"_id": ObjectId(s[key])}, {"file_name": 1})
                    names.add((d or {}).get("file_name") or "")
                if names == wanted:
                    session = s
                    break
            if not session:
                raise SystemExit(
                    f"no manual-check session covers {sorted(wanted)}. Open that pair in a "
                    f"manual-check room and record at least one marking first."
                )
            pair_id = args.pair_id

        markings = await db[MARKINGS].find({"session_id": str(session["_id"])}).to_list(None)
        annotator = args.annotator or str(session.get("annotator") or "")
        if not annotator:
            raise SystemExit("the session has no annotator, and none was given with --annotator")
    finally:
        client.close()

    # Payloads live under the STORAGE root, the manifest under `tests/fixtures/eval`. Two
    # different roots, and `eval_corpus.py` writes worksheets beside the payloads.
    pair_dir = default_payload_dir() / pair_id
    draft, skipped = build_draft(
        markings,
        pair_id=pair_id,
        annotator=annotator,
        ref_entities=_read_entities(pair_dir, "ref"),
        rev_entities=_read_entities(pair_dir, "rev"),
    )

    live = [m for m in markings if not m.get("retracted_at")]
    print(f"[pair]  {pair_id}   session {session['_id']}   annotator {annotator}")
    print(f"[read]  {len(markings)} marking(s), {len(live)} live")
    print(f"[map]   {len(draft['findings'])} finding(s), {len(draft['not_findings'])} non-finding(s)")
    by_status = Counter(f["status"] for f in draft["findings"])
    for status, n in sorted(by_status.items()):
        print(f"          {status:<9} {n}")

    if skipped:
        print(f"\n[!] {len(skipped)} marking(s) could NOT be addressed and are NOT in the draft:")
        for line in skipped:
            print(f"      {line}")
        print("    A label addressed to the wrong entity still scores, so these are refused")
        print("    rather than guessed. Re-record them on an entity that carries a handle, or")
        print("    add them to the draft by hand.")

    out = Path(args.out) if args.out else (default_payload_dir().parent / "worksheets" / f"{pair_id}.labels.draft.json")
    if not args.write:
        print(f"\n[dry-run] nothing written. Re-run with --write to create {out}")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[done] wrote {out}")
    print("[next] install it - this tool deliberately does not, so the validator stays the")
    print("       only thing that can put labels into the manifest:")
    print(f"       tools/eval_corpus.py label --pair-id {pair_id} --from {out}")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Outside the coroutine: argparse raises SystemExit, and inside `asyncio.run` that
    unwinds through the event loop and prints a traceback over the help text."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pair-id", help="corpus pair id, e.g. M7452A1N01")
    ap.add_argument("--session", help="manual-check session id, if you know it")
    ap.add_argument("--annotator", help="override the session's annotator")
    ap.add_argument("--out", help="draft path (default: storage/eval/worksheets/<pair>.labels.draft.json)")
    ap.add_argument("--write", action="store_true", help="write the draft (default: report only)")
    args = ap.parse_args(argv)
    if not args.pair_id and not args.session:
        ap.error("one of --pair-id or --session is required")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(_parse_args())))
