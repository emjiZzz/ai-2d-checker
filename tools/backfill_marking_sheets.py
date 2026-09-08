"""Fill `ref_sheet`/`rev_sheet` on markings written before those fields existed.

Report-only without `--apply`, like `reextract_stale_drawings.py`.

A marking whose drawing still exists gets its file name. A marking whose drawing was purged by a
room deletion cannot get one back -- nothing stores it -- so it gets `deleted drawing <id>`
instead of "". Blank is the state that lets unrelated markings collapse into one another as
duplicate texts, which is the defect this field exists to close; the id at least distinguishes
two deleted sheets from each other and says plainly what happened.

    services/backend/.venv/Scripts/python.exe tools/backfill_marking_sheets.py
    services/backend/.venv/Scripts/python.exe tools/backfill_marking_sheets.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DELETED = "deleted drawing {}"


async def main(apply: bool) -> int:
    from services.backend.domain.models.drawing_document import DrawingDocument
    from services.backend.domain.models.ground_truth import (
        GroundTruthMarking,
        ManualCheckSession,
    )
    from services.backend.infrastructure.database.connection import db_manager

    if not await db_manager.connect(max_retries=1, initial_delay=0.2):
        print("could not connect to the database")
        return 1

    names = {
        str(d.id): (d.file_name or str(d.id))
        for d in await DrawingDocument.find_all().to_list()
        if d.id is not None
    }
    sessions = {str(s.id): s for s in await ManualCheckSession.find_all().to_list()}

    def resolve(drawing_id: str | None) -> str:
        if not drawing_id:
            return ""
        return names.get(str(drawing_id)) or DELETED.format(drawing_id)

    filled = orphaned = already = skipped = 0
    for marking in await GroundTruthMarking.find_all().to_list():
        if marking.ref_sheet or marking.rev_sheet:
            already += 1
            continue

        session = sessions.get(str(marking.session_id))
        ref_id = getattr(marking.ref_address, "drawing_id", None) or (
            session.ref_drawing_id if session else None
        )
        rev_id = getattr(marking.rev_address, "drawing_id", None) or (
            session.rev_drawing_id if session else None
        )
        ref_sheet, rev_sheet = resolve(ref_id), resolve(rev_id)

        if not ref_sheet and not rev_sheet:
            skipped += 1
            continue
        if ref_sheet.startswith("deleted drawing") or rev_sheet.startswith("deleted drawing"):
            orphaned += 1
        else:
            filled += 1

        if apply:
            # $set on the two fields, not a whole-document save: an engineer may be marking
            # against this database right now, and save() would write back every field as it
            # was read.
            await marking.set(
                {
                    GroundTruthMarking.ref_sheet: ref_sheet,
                    GroundTruthMarking.rev_sheet: rev_sheet,
                }
            )

    verb = "filled" if apply else "would fill"
    print(f"{verb}: {filled} from a live drawing, {orphaned} marked as a deleted drawing")
    print(f"already had a sheet: {already}    no drawing id at all: {skipped}")
    if not apply:
        print("\nreport only. re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the resolved names")
    raise SystemExit(asyncio.run(main(parser.parse_args().apply)))
