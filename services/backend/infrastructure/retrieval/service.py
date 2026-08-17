"""Wires the retrieval indexes to their live sources — MongoDB and the vault.

This is the only module in the package that knows about Beanie documents or the vault layout.
`index_builder` deliberately takes already-fetched objects so it stays synchronous and testable
without a database; the async fetching lives here.

**Every rebuild is a whole-corpus rebuild, and that is not laziness.** TF-IDF's idf term is a
property of the *corpus*, not of a document: adding one chunk changes the weight of every n-gram
it contains everywhere else. An incremental "append one vector" would leave the index internally
inconsistent — ranking new chunks under different weights than old ones — which is the kind of
error that produces plausible orderings and no symptom. At this corpus size a full rebuild is
around a second, so correctness is nearly free.

**All CPU work is offloaded.** Every `build_index` call here goes through `asyncio.to_thread`,
because fitting a vocabulary over the corpus blocks the event loop for its whole duration. The
predecessor called indexing inline and got away with it only because its "embedding" was a random
number generator. Guarded by `tests/test_standards_loader_async.py`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...domain.models.audit_violation import RESOLUTION_APPROVED, AuditViolation
from ...domain.models.standard_chunk import StandardChunk
from ...logger import logger
from ..knowledge.vault_sync import VaultSyncManager
from .index_builder import (
    DOMAIN_RULES,
    LESSONS,
    STANDARDS,
    BuildResult,
    build_index,
    records_from_rule_notes,
    records_from_standard_chunks,
    store_for,
)
from .store import IndexStatus, Record

#: Cap on how much of a corpus is pulled into memory for a rebuild. Well above the live corpus;
#: present so that an unexpectedly large collection degrades into a logged truncation rather than
#: an unbounded allocation inside a request handler.
MAX_RECORDS_PER_COLLECTION = 50_000


async def rebuild_standards_index(root: Path | None = None) -> BuildResult:
    """Rebuild the `standards` collection from every StandardChunk in MongoDB."""
    chunks = await StandardChunk.find_all().limit(MAX_RECORDS_PER_COLLECTION).to_list()
    records = records_from_standard_chunks(chunks)
    return await asyncio.to_thread(build_index, STANDARDS, records, root)


async def rebuild_domain_rules_index(root: Path | None = None) -> BuildResult:
    """Rebuild `domain_rules` from the client rule notes in the vault.

    The source directory is gitignored client data and is frequently absent (fresh clone, CI).
    `records_from_rule_notes` returns `[]` in that case and `build_index` declines to write an
    empty index, which leaves the collection reporting MISSING rather than EMPTY — the honest
    distinction between "never built" and "built and found nothing".
    """
    vault = VaultSyncManager.get_instance()
    rules_dir = vault.vault_path / VaultSyncManager.CLIENT_RULES_DIR
    records = await asyncio.to_thread(records_from_rule_notes, rules_dir)
    return await asyncio.to_thread(build_index, DOMAIN_RULES, records, root)


async def rebuild_lessons_index(root: Path | None = None) -> BuildResult:
    """Rebuild `lessons` from supervisor-confirmed violations.

    **The index is derived, not authoritative.** Its source of truth is the `AuditViolation`
    documents themselves, so it can be dropped and rebuilt at any time. That is the structural
    fix for the R0 defect: the old code wrote "lessons" into a *separate* store that nothing else
    populated or verified, so when the write silently failed there was nothing to compare against.
    Deriving the index from records the application already keeps means a failed rebuild is
    recoverable and detectable — the violations are still there.

    Only APPROVED violations are indexed. A rejected finding is a false positive; feeding it back
    as a "lesson" would teach the opposite of what the reviewer said.
    """
    violations = (
        await AuditViolation.find(AuditViolation.resolution_type == RESOLUTION_APPROVED)
        .limit(MAX_RECORDS_PER_COLLECTION)
        .to_list()
    )
    records = [_lesson_record(v) for v in violations]
    records = [r for r in records if r is not None]
    return await asyncio.to_thread(build_index, LESSONS, records, root)


def _lesson_record(violation: AuditViolation) -> Record | None:
    """One confirmed finding as a retrievable lesson.

    `checker_remarks` is included because it is the most valuable part — it is what a human
    actually said about this finding. It is also, per [[ADR-008]], the sharpest privacy edge in
    the system: unbounded free text a person typed, which may quote drawing content verbatim.
    **That is safe at R1 because nothing leaves the machine.** R4 is where anything is
    transmitted, and this field must be stripped at the edge before it is — not at the transport
    layer, where a later refactor could route around it. See
    [[Standards Knowledge — Rule Bundle Format]].
    """
    parts = [
        violation.category,
        violation.description,
        violation.recommendation,
        violation.checker_remarks or "",
    ]
    text = "\n".join(p for p in parts if p and p.strip())
    if not text.strip():
        return None

    return Record(
        id=str(violation.id),
        text=text,
        source="Confirmed finding",
        section=violation.category,
        metadata={
            "audit_session_id": violation.audit_session_id,
            "severity": violation.severity,
            "resolved_at": violation.resolved_at.isoformat() if violation.resolved_at else None,
        },
    )


async def bootstrap_retrieval_indexes(root: Path | None = None) -> dict[str, BuildResult]:
    """Build any collection without a *usable* index. Called once at startup.

    Only builds what is not already good, so a restart does not pay for a rebuild it does not
    need. A collection whose *source* changed while the process was down is not detected here —
    `manifest.source_digest` exists for that, and acting on it is R2/R3 work once there is a
    metric to say whether staleness is actually costing anything.

    **Usable means `IndexStatus.OK`, not "the files are present".** This gated on `store.exists()`
    until 2026-08-14, which checks for a manifest and a records file and nothing about their
    contents — so `INDEX_SCHEMA_VERSION` was inert in practice. An index left behind by an older
    build reported STALE at every `search()` and was never rebuilt by anything, meaning the guard
    that exists to stop an old index being misread instead made the collection permanently
    unsearchable. Bumping the version now actually migrates an install.
    """
    results: dict[str, BuildResult] = {}
    builders = {
        STANDARDS: rebuild_standards_index,
        DOMAIN_RULES: rebuild_domain_rules_index,
        LESSONS: rebuild_lessons_index,
    }

    for collection, rebuild in builders.items():
        status = store_for(collection, root).load()
        if status is IndexStatus.OK:
            logger.debug(f"[retrieval] '{collection}' index is usable; not rebuilding.")
            continue
        if status is not IndexStatus.MISSING:
            logger.info(
                f"[retrieval] '{collection}' index reports {status}; rebuilding it from source."
            )
        try:
            results[collection] = await rebuild(root)
        except Exception as err:  # noqa: BLE001 — startup must not die on an index build
            # Broad by intention, and narrow in effect: this runs during application startup and
            # a retrieval index is not required for the app to serve. The failure is logged with
            # its collection so it is diagnosable, and `query()` will report MISSING rather than
            # returning [] as though it had searched.
            logger.error(f"[retrieval] Failed to build '{collection}' index at startup: {err}")
            results[collection] = BuildResult(collection, 0, built=False, reason=str(err))

    return results
