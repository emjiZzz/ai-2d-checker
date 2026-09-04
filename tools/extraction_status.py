#!/usr/bin/env python
"""Which stored drawings predate the current extraction schema, and what they are missing.

## Why this exists

`EXTRACTION_SCHEMA_VERSION` is stamped onto every `DrawingDocument` as
`extraction_schema_version`, so a drawing written before an extraction-time fix is
*identifiable* without re-reading its entities. CLAUDE.md has carried the same line for weeks:

    Nothing reads it yet -- that is a gap, not permission to leave it stale.

Verified 2026-08-20 and still true: the field is written by `extraction_pipeline.py`,
copied into an `EntityAddress`, and named in a router docstring -- but nothing ever
queries it. So the one question it exists to answer, *"which drawings render and compare
wrong right now?"*, had no way to be asked.

A stale row does not error. `render_paths`, dimension text anchors, leader hooklines, MTEXT
rotation and the elliptical-arc fix are all computed at extraction time, so a drawing
ingested before them renders wrong and keeps rendering wrong until it is re-extracted. It looks
like a drawing the whole time.

## Report only

This never re-extracts. It prints the ids and the endpoint; a human runs it. Same doctrine as
`eval_corpus.py from-manual-check`, which emits a draft and stops -- an automatic bulk
re-extraction is exactly the kind of sweeping change that should not be one command away.

## Where the version descriptions come from

They are parsed out of `extracted_entity.py`'s own `# vN:` block, not restated here. That
block is the source of truth and the next bump will edit it; a second copy in this file would
be correct exactly until v8 and wrong silently thereafter. The parse failing loudly is better
than a stale description reading plausibly -- so an unparseable block is reported, not
defaulted around.

Usage:

    services/backend/.venv/Scripts/python.exe tools/extraction_status.py
    services/backend/.venv/Scripts/python.exe tools/extraction_status.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The version notes are prose lifted from the model file and contain em dashes; this repo's
# drawings live on machines whose console is cp932, where one unencodable character raises
# UnicodeEncodeError and takes the entire report down with it. Degrade the character, never
# the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from services.backend.domain.models.extracted_entity import (  # noqa: E402
    EXTRACTION_SCHEMA_VERSION,
)

MONGO_DB_DEFAULT = "ai_2d_checker"

ENTITY_MODEL = (
    REPO_ROOT / "services" / "backend" / "domain" / "models" / "extracted_entity.py"
)

#: `# v6: leaders carry ...` — the version and the first clause of its note.
_VERSION_NOTE = re.compile(r"^#\s*v(\d+):\s*(.+)$")


def version_notes(source: Path = ENTITY_MODEL) -> dict[int, str]:
    """`{6: "leaders carry `arrow_size` ..."}` parsed from the model's own comment block.

    Continuation lines (a `#` comment that is not itself a `# vN:` header) are folded into the
    note above them, because the block wraps its prose across several lines.
    """
    notes: dict[int, str] = {}
    current: int | None = None
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            if notes:
                break  # past the block; the constant itself follows
            continue
        match = _VERSION_NOTE.match(stripped)
        if match:
            current = int(match.group(1))
            notes[current] = match.group(2).strip()
        elif current is not None:
            notes[current] = f"{notes[current]} {stripped.lstrip('#').strip()}".strip()
    return notes


def _summarise(note: str, width: int = 96) -> str:
    """First sentence of a note, clipped. The full text lives in the model file."""
    sentence = re.split(r"(?<=[.;])\s", note)[0].strip()
    return sentence if len(sentence) <= width else sentence[: width - 3].rstrip() + "..."


def collect(db: Any) -> dict[str, Any]:
    """Group every stored drawing by the schema version it was extracted at."""
    rows: list[dict[str, Any]] = []
    for doc in db["drawing_documents"].find(
        {}, {"filename": 1, "file_name": 1, "extraction_schema_version": 1, "file_hash": 1}
    ):
        raw = doc.get("extraction_schema_version")
        rows.append(
            {
                "id": str(doc.get("_id")),
                "file": str(doc.get("filename") or doc.get("file_name") or "?"),
                # A drawing written before the field existed has no value at all. Reported as
                # `None` rather than coerced to 0, because "never stamped" and "stamped 0" are
                # different facts and only one of them means the pipeline was broken.
                "version": int(raw) if isinstance(raw, int) else None,
                "hash": str(doc.get("file_hash") or "")[:12],
            }
        )
    rows.sort(key=lambda r: (r["version"] is not None, r["version"] or 0, r["file"]))
    return {
        "current": EXTRACTION_SCHEMA_VERSION,
        "drawings": len(rows),
        "by_version": Counter(
            "unstamped" if r["version"] is None else str(r["version"]) for r in rows
        ),
        "stale": [
            r for r in rows
            if r["version"] is None or r["version"] < EXTRACTION_SCHEMA_VERSION
        ],
        "rows": rows,
    }


def print_report(result: dict[str, Any], notes: dict[int, str], limit: int) -> None:
    current = result["current"]
    print(f"\nEXTRACTION_SCHEMA_VERSION = {current}")
    print(f"  drawings stored     {result['drawings']}")
    print(f"  up to date          {result['drawings'] - len(result['stale'])}")
    print(f"  STALE               {len(result['stale'])}")

    if result["by_version"]:
        print("\n  by stored version:")
        for version, count in sorted(
            result["by_version"].items(), key=lambda kv: (kv[0] == "unstamped", kv[0])
        ):
            marker = "" if version == str(current) else "   <-- stale"
            print(f"    v{version:<10} {count:>4}{marker}")

    if not result["stale"]:
        print("\n  Nothing to re-extract.\n")
        return

    print(f"\n  stale drawings (showing {min(limit, len(result['stale']))} "
          f"of {len(result['stale'])}):")
    for row in result["stale"][:limit]:
        stored = "unstamped" if row["version"] is None else f"v{row['version']}"
        print(f"\n    {row['id']}  {stored:<10} {row['file']}")
        missing = [
            v for v in sorted(notes)
            if v > (row["version"] or 0) and v <= current
        ]
        for version in missing:
            print(f"        missing v{version}: {_summarise(notes[version])}")
        if not missing:
            print("        (no recorded note for the versions it is behind)")

    print(
        "\n  To bring one up to date -- keeps the drawing's id, room slot and audit history,\n"
        "  which delete-and-re-upload loses:\n\n"
        "    curl -X POST -H \"Authorization: Bearer $TOKEN\" \\\n"
        "      http://127.0.0.1:8080/api/v1/drawings/<id>/reextract\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="Defaults to the app's configured MONGO_URI, not localhost — this reads what the "
        "running app wrote, and those collections are not in sync_manager's synced set.",
    )
    parser.add_argument("--mongo-db", default=MONGO_DB_DEFAULT)
    parser.add_argument("--limit", type=int, default=20, help="Stale drawings to list.")
    parser.add_argument("--json", type=Path, default=None, help="Write the full status here.")
    args = parser.parse_args()

    try:
        notes = version_notes()
    except OSError as err:
        print(f"Could not read {ENTITY_MODEL}: {err}", file=sys.stderr)
        return 2
    if not notes:
        print(
            f"No `# vN:` notes parsed from {ENTITY_MODEL.name}. The block moved or changed "
            f"shape; fix the parse rather than reporting versions with no descriptions.",
            file=sys.stderr,
        )
        return 2

    uri = args.mongo_uri
    if not uri:
        from services.backend.config import settings

        uri = settings.MONGO_URI

    from pymongo import MongoClient

    try:
        db = MongoClient(uri, serverSelectionTimeoutMS=8000)[args.mongo_db]
        result = collect(db)
    except Exception as err:  # noqa: BLE001 - an unreachable database is a message, not a crash
        print(f"Could not read {args.mongo_db}: {type(err).__name__}: {err}", file=sys.stderr)
        return 2

    print_report(result, notes, args.limit)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {**result, "by_version": dict(result["by_version"])}
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Status written to {args.json}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
