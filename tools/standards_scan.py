#!/usr/bin/env python
"""Triage a folder of candidate standards **before** ingesting any of them.

    services/backend/.venv/Scripts/python.exe tools/standards_scan.py "D:/path/to/standards"
    ... tools/standards_scan.py "D:/standards" --recursive
    ... tools/standards_scan.py file1.xls file2.pdf --per-sheet
    ... tools/standards_scan.py "D:/standards" --json

Runs the **real** `StandardsParser` — the same code the upload endpoint runs — and reports how
much retrievable text each file would actually contribute. Nothing is written: no database, no
copy into the standards sandbox, no index rebuild. Safe to run against a network share.

## Why this exists

A 32.3 MB, 18-sheet `KEMCO and JIS Standards.xls` ingests "successfully" and yields **5,757
characters**, because fourteen of its eighteen sheets hold no text at all — the standards are
screenshots of tables pasted into Excel. Every sheet a checker would consult (`Bolting (KEMCO
Standard)`, `Available Plate Thickness (JIS)`, `Shaft Keyway`) is empty of text.

Nothing in the upload path surfaces that. It reports success, the document appears in the list,
and the corpus is a piping parts list. The cost of finding out per-file, after converting and
uploading an archive, is exactly the cost this script removes.

**The number that matters is bytes-per-character**, not file size. A text-bearing workbook lands
around 10²–10³ bytes per character; one whose content is images lands in the thousands.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# This tool prints Japanese sheet names, and the default Windows console codepage here is cp932,
# which cannot encode them — nor an em dash. Without this the scan dies with UnicodeEncodeError
# *after* doing all the work. See the vault's "Our Own Punctuation Broke on the cp932 Console":
# the same defect, now in the tool written to diagnose Japanese standards.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

from services.backend.infrastructure.audit import standards_parser as sp  # noqa: E402
from services.backend.infrastructure.audit.standards_parser import (  # noqa: E402
    SUPPORTED_STANDARD_FORMATS,
    StandardIngestError,
    StandardsParser,
)

# The parser refuses paths outside the storage sandbox. That guard protects the *upload* path,
# where the filename comes from a client; here the path comes from the operator's own command
# line and the point is to read files that are deliberately elsewhere. Neutralised for this
# process only — this script never writes, so the traversal risk it guards against is absent.
sp.validate_sandboxed_path = lambda p: p

# Above this, the file is overwhelmingly not text. Calibrated on the one real archive available
# (KEMCO: ~5,600 bytes/char, images; its text-bearing sheets: ~100s). A convention, flagged as
# one — not a measured threshold.
BYTES_PER_CHAR_SUSPICIOUS = 2000


def scan_one(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    row: dict[str, Any] = {
        "file": str(path),
        "name": path.name,
        "size_bytes": size,
        "format": path.suffix.lower().lstrip("."),
    }

    if row["format"] not in SUPPORTED_STANDARD_FORMATS:
        row["status"] = "unsupported"
        return row

    try:
        chunks, meta = StandardsParser.parse_file(path)
    except StandardIngestError as err:
        row["status"] = "rejected"
        row["error"] = str(err)
        return row
    except Exception as err:  # a corrupt file must not stop the sweep
        row["status"] = "error"
        row["error"] = f"{type(err).__name__}: {err}"
        return row

    text = "\n".join(c["content"] for c in chunks)
    row.update(
        status="ok",
        chunks=len(chunks),
        characters=len(text),
        sheets_or_pages=meta.get("page_count"),
        images_ignored=meta.get("images_ignored"),
        encoding=meta.get("encoding"),
        cjk=sum(
            1
            for ch in text
            if "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff"
        ),
        severity_markers=sum(
            text.count(m)
            for m in (
                "[INCORRECT / DANGER FLAG]",
                "[CORRECT / STANDARDS COMPLIANT]",
                "[IMPORTANT / ATTENTION REQUIRED]",
            )
        ),
    )
    row["bytes_per_char"] = round(size / len(text)) if text else None

    # Per-sheet breakdown is where an images-only workbook gives itself away: a named sheet
    # holding zero characters is a picture, and its name usually says what was lost.
    if row["format"] in ("xls", "xlsx"):
        per_sheet: dict[str, int] = {}
        for c in chunks:
            name = c["metadata"].get("sheet", "?")
            per_sheet[name] = per_sheet.get(name, 0) + len(c["content"])
        row["sheets_with_text"] = per_sheet

    if not text:
        row["verdict"] = "EMPTY — would be refused at upload"
    elif row["bytes_per_char"] and row["bytes_per_char"] > BYTES_PER_CHAR_SUSPICIOUS:
        row["verdict"] = "MOSTLY IMAGES — ingests, but little is searchable"
    else:
        row["verdict"] = "text-bearing"
    return row


def collect(inputs: list[str], recursive: bool) -> list[Path]:
    out: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            globber = p.rglob if recursive else p.glob
            for fmt in SUPPORTED_STANDARD_FORMATS:
                out.extend(sorted(globber(f"*.{fmt}")))
        elif p.is_file():
            out.append(p)
        else:
            print(f"[warn] not found: {item}", file=sys.stderr)
    # De-duplicate while keeping order; a folder plus an explicit file can overlap.
    seen: set[Path] = set()
    unique = []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def render(rows: list[dict[str, Any]], per_sheet: bool) -> None:
    if not rows:
        print("No candidate files found.")
        return

    print(f"{'file':52} {'MB':>6} {'chars':>8} {'B/char':>7}  verdict")
    print("-" * 104)
    for r in rows:
        mb = r["size_bytes"] / 1e6
        if r["status"] != "ok":
            print(f"{r['name'][:52]:52} {mb:6.1f} {'-':>8} {'-':>7}  {r['status'].upper()}: {r.get('error', '')[:36]}")
            continue
        print(
            f"{r['name'][:52]:52} {mb:6.1f} {r['characters']:8,} "
            f"{(r['bytes_per_char'] or 0):7,}  {r['verdict']}"
        )

    ok = [r for r in rows if r["status"] == "ok"]
    total_chars = sum(r["characters"] for r in ok)
    total_mb = sum(r["size_bytes"] for r in rows) / 1e6
    images = [r for r in ok if r["verdict"].startswith("MOSTLY IMAGES")]
    empty = [r for r in ok if r["verdict"].startswith("EMPTY")]

    print("-" * 104)
    print(f"{len(rows)} file(s), {total_mb:.1f} MB -> {total_chars:,} characters of searchable text")
    if empty:
        print(f"  {len(empty)} would be REFUSED at upload (no extractable text)")
    if images:
        print(f"  {len(images)} are MOSTLY IMAGES — they ingest, but little of them is searchable")
    cjk = sum(r["cjk"] for r in ok)
    markers = sum(r["severity_markers"] for r in ok)
    print(f"  {cjk:,} CJK characters preserved · {markers:,} colour severity markers")

    if per_sheet:
        for r in ok:
            sheets = r.get("sheets_with_text")
            if not sheets:
                continue
            print(f"\n  {r['name']}  ({r['sheets_or_pages']} sheets, {len(sheets)} with text)")
            for name, chars in sorted(sheets.items(), key=lambda kv: -kv[1]):
                print(f"    {name[:44]:44} {chars:7,} chars")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", help="folders and/or files to scan")
    parser.add_argument("-r", "--recursive", action="store_true", help="descend into subfolders")
    parser.add_argument("--per-sheet", action="store_true", help="break each workbook down by sheet")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    files = collect(args.paths, args.recursive)
    rows = [scan_one(f) for f in files]

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    else:
        render(rows, args.per_sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
