"""
One-time destructive cleanup for the room-owned-drawings migration.

Wipes the drawing + room + audit-history data so the app starts from a clean
slate under the new model (every upload is its own drawing; the room owns its
drawings). Deliberately does NOT touch users, sessions, clients, standards, zone
templates, or storage/secure — auth and reference data survive.

Cleared collections:
    rooms, drawings, extracted_entities, extraction_jobs,
    audit_sessions, audit_violations, audit_feedback, annotations

Emptied storage dirs (files removed, dirs kept):
    storage/uploads, storage/renderings, storage/cache, storage/temp

Usage (from the repo root):

    services/backend/.venv/Scripts/python.exe -m services.backend.scripts.wipe_clean --yes

or:

    services/backend/.venv/Scripts/python.exe services/backend/scripts/wipe_clean.py --yes

Without --yes it prints what it *would* do and exits without changing anything.
"""

import argparse
import asyncio
import os
import shutil
import sys

# Repo root is four levels up: scripts/ -> backend/ -> services/ -> <root>.
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)

from services.backend.domain.models.annotation_document import AnnotationDocument
from services.backend.domain.models.audit_feedback import AuditFeedbackDocument
from services.backend.domain.models.audit_session import AuditSession
from services.backend.domain.models.audit_violation import AuditViolation
from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.extraction_job import ExtractionJob
from services.backend.domain.models.room import Room
from services.backend.infrastructure.database.connection import db_manager
from services.backend.infrastructure.storage.path_resolver import get_storage_root

# (label, model) — order is cosmetic; deletions are independent.
TARGET_MODELS = [
    ("rooms", Room),
    ("drawings", DrawingDocument),
    ("extracted_entities", ExtractedEntity),
    ("extraction_jobs", ExtractionJob),
    ("audit_sessions", AuditSession),
    ("audit_violations", AuditViolation),
    ("audit_feedback", AuditFeedbackDocument),
    ("annotations", AnnotationDocument),
]

STORAGE_SUBDIRS = ["uploads", "renderings", "cache", "temp"]


async def _count(model) -> int:
    return await model.find_all().count()


async def wipe(apply: bool) -> None:
    ok = await db_manager.connect()
    if not ok:
        print("ERROR: could not connect to MongoDB — aborting. Nothing was changed.")
        sys.exit(1)

    from services.backend.config import settings

    storage_root = get_storage_root()
    print(f"Database : {settings.MONGO_DB_NAME}")
    print(f"Storage  : {storage_root}")
    print(f"Mode     : {'APPLY (destructive)' if apply else 'DRY RUN (no changes)'}")
    print("-" * 56)

    # 1. Collections
    total_docs = 0
    for label, model in TARGET_MODELS:
        n = await _count(model)
        total_docs += n
        if apply and n:
            await model.find_all().delete()
        print(f"  {'deleted' if apply else 'would delete'} {n:>6} {label}")

    # 2. Storage directories
    print("-" * 56)
    total_files = 0
    for sub in STORAGE_SUBDIRS:
        d = storage_root / sub
        if not d.exists():
            print(f"  (skip) {sub} — not present")
            continue
        entries = list(d.iterdir())
        total_files += len(entries)
        if apply:
            for entry in entries:
                try:
                    if entry.is_dir():
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
                except Exception as e:  # best-effort; keep going
                    print(f"    ! failed to remove {entry}: {e}")
        print(f"  {'emptied' if apply else 'would empty'} {sub} ({len(entries)} entries)")

    print("-" * 56)
    if apply:
        print(f"Done. Removed {total_docs} documents and cleared {total_files} storage entries.")
    else:
        print(
            f"Dry run: {total_docs} documents and {total_files} storage entries would be removed.\n"
            "Re-run with --yes to apply."
        )

    await db_manager.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Wipe drawing/room/history data for a clean slate.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag the script only reports what it would do.",
    )
    args = parser.parse_args()
    asyncio.run(wipe(apply=args.yes))


if __name__ == "__main__":
    main()
