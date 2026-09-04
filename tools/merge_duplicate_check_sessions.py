#!/usr/bin/env python
"""Reunite manual-check markings scattered across duplicate sessions - one-off repair.

    services/backend/.venv/Scripts/python.exe tools/merge_duplicate_check_sessions.py
    ... tools/merge_duplicate_check_sessions.py --apply
    ... tools/merge_duplicate_check_sessions.py --apply --delete-drained

## What it repairs

Until 2026-08-18 `POST /ground-truth/sessions` inserted a new session on every call, and the
desktop client calls it every time the manual-check workspace mounts. So each app reload minted
an empty session for the same pair, and the side panel -- which lists the markings of whichever
session the open returned -- came up blank. Nothing was deleted: the engineer's markings stayed
in `ground_truth_markings`, addressed to a session id nothing would ask for again.

The endpoint is idempotent now, so no new duplicates appear. This moves the stranded markings
onto the session that endpoint will actually resume, which is the OLDEST `in_progress` session
for a (room, reference, revision, annotator). Picking the same session as the endpoint is the
whole point -- merging onto any other one would leave the panel just as empty.

## What it will not do

* Touch a `submitted` session, in either direction. A submitted session is a finished pass and a
  human statement about it; growing one after the fact would rewrite a record, and draining one
  would destroy it. Groups whose sessions are all submitted are skipped and reported.
* Delete anything unless asked (`--delete-drained`), and even then only a session with no
  markings left and no pair-level notes. A note is an engineer's narrative and there is nowhere
  to merge one without inventing a rule about whose prose wins.
* Write at all without `--apply`. The default run reports the plan and exits.

Read `--apply` as irreversible: markings are re-addressed in place, and there is no undo beyond
restoring the collection.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# A drawing id, a room name or an annotator can be Japanese, and this repo's console is cp932 —
# `print` would raise UnicodeEncodeError partway through the report and abort a repair run at an
# arbitrary point. `errors="replace"` cannot crash: the worst case is a `?` in a name.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, OSError):  # not a real console (piped, redirected, or captured)
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.config import settings  # noqa: E402

SESSIONS = "manual_check_sessions"
MARKINGS = "ground_truth_markings"

#: What makes two sessions "the same check". Must stay identical to the resume query in
#: `api/routers/ground_truth.create_session` — if this groups more loosely than the endpoint
#: matches, the merge consolidates onto a session the app will never resume, and the panel stays
#: empty with the markings now in a *third* place.
GROUP_KEYS = ("room_id", "ref_drawing_id", "rev_drawing_id", "annotator")


async def _connect():
    """Primary URI, then the local fallback — the same two candidates the app tries.

    Deliberately not `DatabaseConnectionManager.connect()`: that initialises Beanie for every
    model and seeds default admin/engineer accounts on an empty database. A repair script must
    not create users as a side effect of being run against the wrong host.
    """
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
            return client, uri
        except Exception as err:  # noqa: BLE001 — any failure means try the next candidate
            last = err
            client.close()
    raise RuntimeError(f"no reachable MongoDB in {candidates}: {last}")


def _plan(sessions: list[dict[str, Any]], counts: dict[str, int]) -> list[dict[str, Any]]:
    """Group the open sessions and decide which one each group collapses onto.

    Pure, so the grouping and the choice of canonical are testable without a database.
    """
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        if s.get("status") != "in_progress":
            continue
        groups[tuple(s.get(k) for k in GROUP_KEYS)].append(s)

    plans = []
    for key, members in sorted(groups.items(), key=lambda kv: [str(p) for p in kv[0]]):
        if len(members) < 2:
            continue
        # Oldest first, matching the endpoint. `started_at` is always set by the model default,
        # but sort on the id as a tiebreak so two sessions opened in the same millisecond — which
        # a fast double-mount can produce — still order deterministically.
        members.sort(key=lambda s: (s["started_at"], str(s["_id"])))
        canonical, *drained = members
        plans.append(
            {
                "key": dict(zip(GROUP_KEYS, key, strict=True)),
                "canonical": canonical,
                "drained": [
                    {
                        "session": d,
                        "markings": counts.get(str(d["_id"]), 0),
                        "notes": (d.get("notes") or "").strip(),
                    }
                    for d in drained
                ],
            }
        )
    return plans


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Outside the coroutine on purpose.

    `--help` and a bad flag both raise `SystemExit` from argparse. Raised inside `asyncio.run`
    that unwinds through the event loop and prints a traceback over the help text, which makes a
    repair tool look broken at the exact moment someone is checking what it does.
    """
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true", help="perform the writes (default: report only)")
    ap.add_argument(
        "--delete-drained",
        action="store_true",
        help="with --apply, remove drained sessions that hold no markings and no notes",
    )
    ap.add_argument("--room", help="limit to one room id")
    return ap.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    client, uri = await _connect()
    try:
        db = client[settings.MONGO_DB_NAME]
        query = {"room_id": args.room} if args.room else {}
        sessions = await db[SESSIONS].find(query).to_list(length=None)

        # One pass over the markings rather than a count per session: a query per duplicate is
        # slow on a collection this shape and tells us nothing extra.
        counts: dict[str, int] = defaultdict(int)
        live_counts: dict[str, int] = defaultdict(int)
        async for m in db[MARKINGS].find({}, {"session_id": 1, "retracted_at": 1}):
            sid = str(m.get("session_id"))
            counts[sid] += 1
            if not m.get("retracted_at"):
                live_counts[sid] += 1

        print(f"[db] {settings.MONGO_DB_NAME} at {uri.split('@')[-1]}")
        print(f"[scan] {len(sessions)} session(s), {sum(counts.values())} marking(s)")

        submitted = [s for s in sessions if s.get("status") == "submitted"]
        if submitted:
            print(f"[skip] {len(submitted)} submitted session(s) - never merged, see module docstring")

        plans = _plan(sessions, counts)
        if not plans:
            print("[ok] no duplicate open sessions. Nothing to merge.")
            return 0

        movable = sum(d["markings"] for p in plans for d in p["drained"])
        print(f"\n[plan] {len(plans)} pair(s) with duplicates, {movable} marking(s) to re-address\n")

        for p in plans:
            k = p["key"]
            canon = p["canonical"]
            print(f"  room {k['room_id']}  {k['ref_drawing_id']} -> {k['rev_drawing_id']}  ({k['annotator']})")
            print(
                f"    keep  {canon['_id']}  started {canon['started_at']}  "
                f"{counts.get(str(canon['_id']), 0)} marking(s)"
            )
            for d in p["drained"]:
                note = "  (!) has notes, will not be deleted" if d["notes"] else ""
                print(f"    move  {d['session']['_id']}  {d['markings']} marking(s){note}")

        if not args.apply:
            print("\n[dry-run] nothing written. Re-run with --apply to perform the merge.")
            return 0

        moved = 0
        removed = 0
        for p in plans:
            canonical_id = str(p["canonical"]["_id"])
            for d in p["drained"]:
                res = await db[MARKINGS].update_many(
                    {"session_id": str(d["session"]["_id"])},
                    {"$set": {"session_id": canonical_id}},
                )
                moved += res.modified_count
                live_counts[canonical_id] += live_counts.get(str(d["session"]["_id"]), 0)

                if args.delete_drained and d["markings"] == 0 and not d["notes"]:
                    await db[SESSIONS].delete_one({"_id": d["session"]["_id"]})
                    removed += 1

            # Recomputed from the rows, never incremented — the same rule `_recount` uses in the
            # router, and for the same reason: a counter that is adjusted rather than counted
            # drifts the first time a write fails halfway.
            live = await db[MARKINGS].count_documents(
                {"session_id": canonical_id, "retracted_at": None}
            )
            await db[SESSIONS].update_one(
                {"_id": p["canonical"]["_id"]}, {"$set": {"marking_count": live}}
            )

        print(f"\n[done] re-addressed {moved} marking(s); deleted {removed} drained session(s).")
        print("[next] reopen the room - the panel should list the markings again.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(_parse_args())))
