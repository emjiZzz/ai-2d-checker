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

from ...domain.models.audit_feedback import AuditFeedbackDocument
from ...domain.models.audit_violation import (
    RESOLUTION_APPROVED,
    RESOLUTION_REJECTED,
    AuditViolation,
)
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.standard_chunk import StandardChunk
from ...logger import logger
from ..knowledge.vault_sync import VaultSyncManager
from ..learning.config import MODEL_DIRNAME
from .index_builder import (
    CORRECTIONS,
    DOMAIN_RULES,
    ENTITIES,
    FINDINGS,
    LESSONS,
    STANDARDS,
    VAULT,
    BuildResult,
    build_index,
    records_from_entities,
    records_from_rule_notes,
    records_from_standard_chunks,
    records_from_vault_notes,
    store_for,
)
from .store import IndexStatus, Record

#: Cap on how much of a corpus is pulled into memory for a rebuild. Well above the live corpus;
#: present so that an unexpectedly large collection degrades into a logged truncation rather than
#: an unbounded allocation inside a request handler.
MAX_RECORDS_PER_COLLECTION = 50_000

#: One lock per collection, so a rebuild of `lessons` never overlaps another rebuild of
#: `lessons` — while still letting different collections build concurrently at startup.
#:
#: `review_violation` rebuilds `lessons` on **every** supervisor verdict, and the build itself
#: runs in a worker thread (`asyncio.to_thread`), so two verdicts submitted close together
#: genuinely execute `VectorStore.write` in parallel. The writes are atomic per file now, which
#: bounds the damage to "one run's files win"; this removes the interleaving entirely so the
#: winner is the *later* build rather than whichever thread happened to finish each rename last.
_REBUILD_LOCKS: dict[str, asyncio.Lock] = {}


def _rebuild_lock(collection: str) -> asyncio.Lock:
    lock = _REBUILD_LOCKS.get(collection)
    if lock is None:
        lock = asyncio.Lock()
        _REBUILD_LOCKS[collection] = lock
    return lock


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
    async with _rebuild_lock(LESSONS):
        violations = (
            await AuditViolation.find(AuditViolation.resolution_type == RESOLUTION_APPROVED)
            .limit(MAX_RECORDS_PER_COLLECTION)
            .to_list()
        )
        records = [violation_record(v) for v in violations]
        records = [r for r in records if r is not None]
        return await asyncio.to_thread(build_index, LESSONS, records, root)


async def rebuild_vault_index(root: Path | None = None) -> BuildResult:
    """Rebuild `vault` from the Obsidian knowledge base, minus two directories.

    The exclusions are derived from their owners rather than restated: `CLIENT_RULES_DIR` is
    already the `domain_rules` collection, and `MODEL_DIRNAME` is a gitignored generated
    artifact. Hardcoding either string here would leave a copy free to drift from the module
    that defines it.
    """
    vault = VaultSyncManager.get_instance()
    excluded = frozenset({VaultSyncManager.CLIENT_RULES_DIR, MODEL_DIRNAME})
    records = await asyncio.to_thread(
        records_from_vault_notes, vault.vault_path, excluded
    )
    return await asyncio.to_thread(build_index, VAULT, records, root)


async def rebuild_entities_index(root: Path | None = None) -> BuildResult:
    """Rebuild `entities` from every extracted entity carrying text.

    Drawing names are fetched once and passed down so a citation can name the sheet rather than
    a 32-character id. Fetched whole rather than projected: this collection is tens of drawings
    against thousands of entities, so the drawings are not where the cost is.

    ⚠ **Customer drawing content.** Client-local, local-only at R1.
    """
    drawings = await DrawingDocument.find_all().to_list()
    names = {str(d.id): d.file_name for d in drawings}

    entities = await ExtractedEntity.find_all().limit(MAX_RECORDS_PER_COLLECTION).to_list()
    records = await asyncio.to_thread(records_from_entities, entities, names)
    return await asyncio.to_thread(build_index, ENTITIES, records, root)


async def rebuild_corrections_index(root: Path | None = None) -> BuildResult:
    """Rebuild `corrections` from every human correction that has not been taken back.

    This is the highest-signal collection in the system: every record is a person saying the
    engine got something wrong, and unlike `lessons` it is not restricted to findings a
    supervisor happened to route through the review queue.

    **Retracted rows are dropped by `feedback_record`, not filtered here**, so the "a retracted
    correction teaches nothing" rule has exactly one implementation on the retrieval side and
    reads the same as `trainer.build_bundle`'s.
    """
    docs = await AuditFeedbackDocument.find_all().limit(MAX_RECORDS_PER_COLLECTION).to_list()
    records = [r for r in (feedback_record(d) for d in docs) if r is not None]
    return await asyncio.to_thread(build_index, CORRECTIONS, records, root)


async def rebuild_findings_index(root: Path | None = None) -> BuildResult:
    """Rebuild `findings` from **every** violation, reviewed or not.

    ⚠ **This collection is mostly unreviewed engine output, and that is the point of indexing it
    separately from `lessons` rather than widening `lessons`.** `lessons` answers *"what has a
    human confirmed"*; this answers *"has this system ever reported anything like this"*. Each
    record's `Record.source` states its review state, so a citation cannot present an unreviewed
    finding as a confirmed one.

    Kept separate from `lessons` — of which it is a strict superset — because
    `metrics.chance_recall_at_k` is `k/N` over a single collection's own record count. Merging
    them would destroy the one collection whose trust level is unambiguous.
    """
    violations = await AuditViolation.find_all().limit(MAX_RECORDS_PER_COLLECTION).to_list()
    records = [r for r in (violation_record(v) for v in violations) if r is not None]
    return await asyncio.to_thread(build_index, FINDINGS, records, root)


#: How a violation's review state is spoken in its citation. In `Record.source` rather than only
#: in metadata because `source` is what `Record.citation()` renders, and a hit that does not say
#: whether a human ever agreed with it is the hazard [[ADR-008]] named for retrieval:
#: *"surfacing near-miss rules as authoritative is a recall attack"*.
REVIEW_STATE_SOURCE = {
    RESOLUTION_APPROVED: "Confirmed finding",
    RESOLUTION_REJECTED: "Rejected finding",
}
UNREVIEWED_SOURCE = "Unreviewed finding"


def violation_record(violation: AuditViolation) -> Record | None:
    """One audit violation as a retrievable record.

    Generalised from `_lesson_record` on 2026-08-17 so that `lessons` and `findings` cannot
    drift apart on how a violation becomes text — two copies of that rule would keep working
    while slowly disagreeing, which is the expensive shape in this codebase.

    **The text is byte-identical to what `_lesson_record` produced.** That is deliberate and is
    what keeps the `lessons` `source_digest` stable across this change: `index_builder._digest`
    hashes texts only, so any label set authored against `lessons` survives. `resolution_type`
    was added to *metadata*, which the digest does not cover — verified, not assumed.

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
        source=REVIEW_STATE_SOURCE.get(violation.resolution_type, UNREVIEWED_SOURCE),
        section=violation.category,
        metadata={
            "audit_session_id": violation.audit_session_id,
            "severity": violation.severity,
            "resolved_at": violation.resolved_at.isoformat() if violation.resolved_at else None,
            "resolution_type": violation.resolution_type,
        },
    )


def feedback_record(feedback: AuditFeedbackDocument) -> Record | None:
    """One human correction as a retrievable record.

    **A retracted correction is not indexed.** Same rule `trainer.build_bundle` applies for
    training: a correction the human took back teaches nothing, and the collection keeps the row
    only as an audit trail of who taught the model what. Indexing it would let a withdrawn
    judgement be cited back at the next checker as though it still stood.

    ⚠ **`client_name` is metadata, not a filter.** Nothing here scopes retrieval to one client,
    so a query can surface another client's correction. That is the same cross-client
    contamination `AutoDocEngine` was fixed for on 2026-08-10 — it is *not* reintroduced here
    (this path writes no rules and suppresses no findings), but a consumer that turns a hit into
    a rule must scope on this field. Recorded so the next caller does not have to rediscover it.

    ⚠ **`human_comment` carries the same privacy edge as `checker_remarks`** — see
    `violation_record`. Local-only at R1; strip at the edge before anything is transmitted.
    """
    if getattr(feedback, "retracted_at", None):
        return None

    entity_text = (feedback.entity_text or "").strip()
    comment = (feedback.human_comment or "").strip()
    if not entity_text and not comment:
        # Category plus a verb is not retrievable by any real query, and it would collapse
        # against every other verdict-only row in the same category anyway.
        return None

    # The verb goes in the indexed *text*, not only in metadata. Two corrections on the same
    # entity text that reached opposite verdicts are two answers to a query; with the verb in
    # metadata alone their texts are byte-identical and `_collapse_duplicate_texts` keeps one —
    # silently discarding the disagreement, which is the most informative row in the corpus.
    # ASCII arrow deliberately: citations are printed, and this console is cp932. See
    # [[Gotcha - Our Own Punctuation Broke on the cp932 Console]].
    verdict = (
        f"Human correction: {feedback.original_status} -> {feedback.human_corrected_status}"
    )
    detail = ""
    if feedback.corrected_category:
        detail = f"Recategorised as {feedback.corrected_category}"
    elif feedback.corrected_value:
        detail = f"Corrected value: {feedback.corrected_value}"

    parts = [feedback.category, entity_text, verdict, detail, comment]
    text = "\n".join(p for p in parts if p and p.strip())

    return Record(
        id=str(feedback.id),
        text=text,
        source="Human correction",
        section=feedback.category,
        metadata={
            "drawing_id": feedback.drawing_id,
            "session_id": feedback.session_id,
            "client_name": feedback.client_name,
            "original_status": feedback.original_status,
            "human_corrected_status": feedback.human_corrected_status,
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
        CORRECTIONS: rebuild_corrections_index,
        FINDINGS: rebuild_findings_index,
        VAULT: rebuild_vault_index,
        ENTITIES: rebuild_entities_index,
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
