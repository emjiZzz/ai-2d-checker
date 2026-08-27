#!/usr/bin/env python
"""Bring every stale drawing up to the current EXTRACTION_SCHEMA_VERSION.

    services/backend/.venv/Scripts/python.exe tools/reextract_stale_drawings.py
    ... tools/reextract_stale_drawings.py --apply
    ... tools/reextract_stale_drawings.py --apply --limit 5

## Why this exists as a tool rather than a one-off loop

`tools/extraction_status.py` reports which drawings are stale and deliberately never fixes any.
That left the cure as "call `POST /drawings/{id}/reextract` 38 times by hand", which is the kind
of thing that gets done once, half-finished, and never repeated -- and it has to be repeated
**every time `EXTRACTION_SCHEMA_VERSION` is bumped**, because a bump is precisely the act that
makes rows stale.

Staleness is not cosmetic. `render_paths`, dimension text anchors, leader hooklines, leader
arrowheads, MTEXT rotation and the angular-dimension degree conversion are computed at
EXTRACTION time, so a stale drawing renders wrong while looking like a perfectly ordinary sheet.
An engineer marking one up for ground truth is reading missing arrowheads, short leader landings
and a dimension that says `1.05` where the paper says `60`.

## What it does and does not do

* **Reuses `extraction_status.collect`** rather than restating the staleness rule. Two copies of
  "which rows are behind" is the drift this repo keeps paying for, and here the copies would
  disagree silently -- one tool reporting clean while the other re-extracts nothing.
* **Writes nothing without `--apply`.** The default run prints the plan and exits, matching
  `merge_duplicate_check_sessions.py`.
* **One at a time, waiting for each job to finish.** `ExtractionPipeline.run` REPLACES a
  drawing's entities, and the route answers 409 while an extraction is already running; firing 38
  in parallel would collide with both.
* **Never deletes.** A failed re-extraction leaves the drawing exactly as it was -- the previous
  entities stay readable until the new parse succeeds -- so a failure here is safe to retry.

## The two expected failures

* **422** -- the stored source file is gone. There are more `DrawingDocument` rows than files in
  `storage/uploads`, so some rows cannot be re-extracted at all. Reported, not fatal: nothing can
  be done for them from here and stopping the run would leave the fixable ones behind.
* **409** -- an extraction is already running. Waited out rather than skipped.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.backend.core.security import initialize_local_api_token  # noqa: E402
from tools.extraction_status import MONGO_DB_DEFAULT, collect  # noqa: E402

#: Matches `connectionStore.ts`, which defaults to 8080 rather than FastAPI's usual 8000.
DEFAULT_BASE = "http://127.0.0.1:8080"

#: A single sheet parses in seconds; this is a ceiling for a pathological one, not a target.
JOB_TIMEOUT_SEC = 300
POLL_SEC = 2.0


def _poll(base: str, headers: dict[str, str], job_id: str) -> tuple[str, str]:
    """Block until the job leaves a running state. Returns (status, message)."""
    deadline = time.time() + JOB_TIMEOUT_SEC
    while time.time() < deadline:
        r = requests.get(f"{base}/api/v1/jobs/{job_id}", headers=headers, timeout=30)
        if r.status_code != 200:
            return "unknown", f"poll HTTP {r.status_code}"
        job = r.json().get("data") or {}
        status = str(job.get("status") or "")
        if status in {"completed", "success", "succeeded"}:
            return "completed", ""
        if status in {"failed", "error"}:
            return "failed", str(job.get("error_message") or "no message")
        time.sleep(POLL_SEC)
    return "timeout", f"still running after {JOB_TIMEOUT_SEC}s"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually re-extract; default reports only")
    ap.add_argument("--limit", type=int, default=0, help="stop after N drawings (0 = all)")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"backend base URL (default {DEFAULT_BASE})")
    ap.add_argument("--mongo-uri", default=None,
                    help="Defaults to the app's configured MONGO_URI, matching "
                         "extraction_status.py -- this must read the same database the "
                         "running backend writes, or it re-extracts the wrong estate.")
    ap.add_argument("--mongo-db", default=MONGO_DB_DEFAULT)
    args = ap.parse_args()

    uri = args.mongo_uri
    if not uri:
        from services.backend.config import settings

        uri = settings.MONGO_URI

    from pymongo import MongoClient

    try:
        db = MongoClient(uri, serverSelectionTimeoutMS=8000)[args.mongo_db]
        result: dict[str, Any] = collect(db)
    except Exception as err:  # noqa: BLE001 - an unreachable database is a message, not a crash
        print(f"Could not read {args.mongo_db}: {type(err).__name__}: {err}", file=sys.stderr)
        return 2
    stale = result["stale"]
    if args.limit:
        stale = stale[: args.limit]

    print(f"\nEXTRACTION_SCHEMA_VERSION = {result['current']}")
    print(f"  drawings stored     {result['drawings']}")
    print(f"  STALE               {len(result['stale'])}"
          + (f"  (limited to {len(stale)} this run)" if args.limit else ""))

    if not stale:
        print("\n  Nothing to do -- every stored drawing is current.\n")
        return 0

    if not args.apply:
        print("\n  DRY RUN -- nothing will be written. Re-run with --apply.\n")
        for row in stale:
            print(f"    {row['id']}  v{row['version'] if row['version'] is not None else '?':<3} {row['file']}")
        print(f"\n  {len(stale)} drawing(s) would be re-extracted, one at a time.\n")
        return 0

    token = initialize_local_api_token()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        health = requests.get(f"{args.base}/api/v1/system/status", headers=headers, timeout=10)
        reachable = health.status_code < 500
    except requests.RequestException as exc:
        print(f"\n  Backend not reachable at {args.base}: {exc}")
        print("  Start it first -- this tool drives the route, it does not re-extract in-process.\n")
        return 1
    if not reachable:
        print(f"\n  Backend at {args.base} answered HTTP {health.status_code}.\n")
        return 1

    print(f"\n  Re-extracting {len(stale)} drawing(s) via {args.base}, one at a time.\n")
    done, failed, missing = 0, [], []

    for i, row in enumerate(stale, 1):
        did, name = row["id"], row["file"]
        label = f"  [{i}/{len(stale)}] {name[:46]:<46}"

        while True:
            r = requests.post(f"{args.base}/api/v1/drawings/{did}/reextract", headers=headers, timeout=60)
            if r.status_code != 409:
                break
            print(f"{label} waiting (another extraction is running)")
            time.sleep(POLL_SEC * 2)

        if r.status_code == 422:
            # Source file gone. Nothing to do from here; keep going so the fixable ones land.
            missing.append((did, name))
            print(f"{label} SKIP  source file missing")
            continue
        if r.status_code >= 400:
            failed.append((did, name, f"HTTP {r.status_code}"))
            print(f"{label} FAIL  HTTP {r.status_code}")
            continue

        job_id = ((r.json().get("data") or {}).get("id")) or ""
        if not job_id:
            failed.append((did, name, "no job id in response"))
            print(f"{label} FAIL  no job id")
            continue

        status, message = _poll(args.base, headers, job_id)
        if status == "completed":
            done += 1
            print(f"{label} ok")
        else:
            failed.append((did, name, f"{status}: {message}"))
            print(f"{label} FAIL  {status}: {message}")

    print(f"\n  re-extracted   {done}")
    print(f"  skipped        {len(missing)}  (source file gone)")
    print(f"  failed         {len(failed)}")
    for did, name, why in failed:
        print(f"      {did}  {name}  -- {why}")
    print("\n  Re-run tools/extraction_status.py to confirm.\n")

    # A missing source file is a fact about the estate, not a failure of this run.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
