import re
import time
from datetime import UTC, datetime

from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.standard_chunk import StandardChunk
from ...domain.models.standard_document import StandardDocument
from ...logger import logger
from .. import retrieval
from ..retrieval.queries import build_drawing_keywords, drawing_query_text, layer_names_for
from .ai_engine import AIEngine
from .confidence import ConfidenceScorer
from .rule_engine import RuleEngine
from .violation_detector import ViolationDetector


class AuditOrchestrator:
    """
    Orchestrates the drawing compliance audit.
    Manages operational lifecycles, executes rule checking and AI comparative analysis,
    calculates metrics, and saves results in MongoDB.
    """

    @staticmethod
    async def run_audit(drawing_id: str, standard_id: str | None, session_id: str, client_name: str | None = None) -> tuple[AuditSession, int]:
        """
        Executes standard-based compliance auditing.
        Returns:
            session: Updated AuditSession document.
            violation_count: Total consolidated violations saved.
        """
        start_time = time.time()
        logger.info(f"Triggering standard compliance audit: Drawing {drawing_id} vs Standard {standard_id}, Client {client_name} (Session: {session_id})")

        # 1. Fetch matching models and validate status
        session = await AuditSession.get(session_id)
        if not session:
            raise FileNotFoundError(f"Target AuditSession not registered: {session_id}")

        drawing = await DrawingDocument.get(drawing_id)
        if not drawing:
            session.status = "failed"
            session.error_message = f"Drawing document not found: {drawing_id}"
            session.completed_at = datetime.now(UTC)
            await session.save()
            raise FileNotFoundError(session.error_message)

        # Retrieve the applicable standards
        standards_to_evaluate = []
        if client_name:
            # 1. Fetch Universal standards (scope == "universal")
            universal_stds = await StandardDocument.find(StandardDocument.scope == "universal").to_list()
            standards_to_evaluate.extend(universal_stds)
            # 2. Fetch Client-Specific standards (scope == "client_specific" and client_name == client_name)
            client_stds = await StandardDocument.find(
                StandardDocument.scope == "client_specific",
                StandardDocument.client_name == client_name.upper()
            ).to_list()
            standards_to_evaluate.extend(client_stds)
        elif standard_id:
            standard = await StandardDocument.get(standard_id)
            if standard:
                standards_to_evaluate.append(standard)

        if not standards_to_evaluate:
            session.status = "failed"
            session.error_message = f"No engineering standards or rules matched for client '{client_name}' or standard '{standard_id}'."
            session.completed_at = datetime.now(UTC)
            await session.save()
            raise FileNotFoundError(session.error_message)

        # For AI engine calls, use primary client standard or consolidated mock as standard parameter
        primary_standard = standards_to_evaluate[0]

        # 2. Update session state to processing
        session.status = "processing"
        session.started_at = datetime.now(UTC)
        await session.save()

        try:
            # 3. Retrieve standard grounded sections (RAG chunks) for all matching standards
            standard_ids = [str(s.id) for s in standards_to_evaluate]
            grounding_chunks = await StandardChunk.find({"standard_id": {"$in": standard_ids}}).to_list()
            logger.info(f"Retrieved {len(grounding_chunks)} grounded chunks from {len(standards_to_evaluate)} applicable Standards.")

            # 4. Trigger Deterministic CAD Rule Engine
            rule_start = time.time()
            rule_violations = await RuleEngine.validate_drawing(session_id, drawing)
            rule_duration = time.time() - rule_start
            logger.info(f"CAD Rule Engine complete in {rule_duration:.4f}s. Detected {len(rule_violations)} infractions.")

            # 4.5 RAG — Retrieve historically-relevant lessons from past reviews
            # Builds a keyword query from the drawing's layer names and entity types,
            # then fetches matching StandardChunk snippets to inject as context.
            rag_start = time.time()
            lessons_learned = await AuditOrchestrator._retrieve_lessons_learned(
                drawing=drawing,
                standard_ids=standard_ids
            )
            rag_duration = time.time() - rag_start
            logger.info(
                f"RAG retrieval complete in {rag_duration:.4f}s. "
                f"Injecting {len(lessons_learned)} contextual lesson(s) into AI context window."
            )

            # 5. Trigger Grounded Gemini Vision Orchestrator (with RAG context injected)
            ai_start = time.time()
            ai_violations = await AIEngine.audit_drawing(
                session_id, drawing, primary_standard, grounding_chunks,
                lessons_learned=lessons_learned
            )
            ai_duration = time.time() - ai_start
            logger.info(f"Gemini Vision Orchestrator complete in {ai_duration:.4f}s. Detected {len(ai_violations)} infractions.")

            # 6. Consolidate and Deduplicate Violations
            consolidated = ViolationDetector.consolidate_violations(rule_violations, ai_violations)

            # 7. Compute Scores
            compliance = ConfidenceScorer.calculate_compliance_score(consolidated)
            confidence = ConfidenceScorer.calculate_average_confidence(consolidated)

            # 8. Save Violations to MongoDB
            if consolidated:
                # Add session_id reference and save
                for v in consolidated:
                    v.audit_session_id = session_id
                await AuditViolation.insert_many(consolidated)

            # 9. Update Session timings and statistics
            total_duration = time.time() - start_time
            session.status = "completed"
            session.compliance_score = compliance
            session.confidence_score = confidence
            session.timings = {
                "rule_engine_seconds": round(rule_duration, 4),
                "ai_engine_seconds": round(ai_duration, 4),
                "total_seconds": round(total_duration, 4)
            }
            session.diagnostics = {
                "grounding_chunks_evaluated": len(grounding_chunks),
                "rule_violations_count": len(rule_violations),
                "ai_violations_count": len(ai_violations),
                "consolidated_violations_count": len(consolidated)
            }
            session.completed_at = datetime.now(UTC)
            await session.save()

            logger.info(f"Compliance audit complete for session {session_id} in {total_duration:.4f}s. Compliance: {compliance}%.")
            return session, len(consolidated)

        except Exception as e:
            logger.error(f"Audit pipeline execution crashed: {str(e)}")
            session.status = "failed"
            session.error_message = str(e)
            session.completed_at = datetime.now(UTC)
            await session.save()
            raise

    # ------------------------------------------------------------------
    # RAG Retrieval Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _retrieve_lessons_learned(
        drawing: DrawingDocument,
        standard_ids: list[str],
        top_k: int = 5
    ) -> list[StandardChunk]:
        """The StandardChunk clauses most relevant to this drawing, capped at `top_k`.

        Ranked by the local lexical index (R1, ADR-008) on keywords from layer names, the entity
        types in `entity_counts`, and the file name stem. Lexical, not semantic: char n-gram
        TF-IDF cosine, so it matches `ユニット No` against `ユニットNo.` and tolerates a typo but
        cannot match a synonym or an English term against its Japanese equivalent. Say lexical.
        This docstring said "semantically relevant" while the vector stage was seeded noise --
        ADR-008, which is also why a dense encoder must beat this on R2 before it ships.

        Falls back to substring matching if the index is unbuilt; `_retrieve_via_lexical_index`
        says why an absent index must not look like an empty result.
        """
        # The query is built in `retrieval.queries.build_drawing_query`, not here, so the Stage B
        # harvester cannot measure a query production does not search with. See [[ADR-012]].
        #
        # Layer names come from `ExtractedEntity.layer`, not `drawing.metadata["layers"]` -- a key
        # nothing writes, which silently emptied the strongest signal on all 44 drawings.
        # See [[Gotcha - The Strongest Signal in the Audit Query Was Never Written]].
        #
        # The layer fetch stays INSIDE the try below. Lessons retrieval is non-fatal by design, and
        # hoisting a Mongo round trip out of that guard lets a transient DB error crash a whole
        # audit for a context-window nicety. It did, for one commit, and a test caught it.
        try:
            layer_names = await layer_names_for(str(drawing.id))
            unique_keywords = build_drawing_keywords(drawing, layer_names)
            if not unique_keywords:
                logger.debug(
                    "RAG: No keywords extracted from drawing metadata. Skipping lessons retrieval."
                )
                return []

            query_text = drawing_query_text(drawing.file_name, unique_keywords)
            logger.debug(f"RAG: Querying StandardChunks with keywords: {unique_keywords}")

            # R1 (ADR-008): rank with the local lexical index. Char n-gram TF-IDF, exact
            # cosine, offline. This is the stage that R0 emptied — the version before it
            # searched hash-seeded noise and logged "Retrieved N semantic match(es)".
            ranked = await AuditOrchestrator._retrieve_via_lexical_index(
                query_text=query_text,
                standard_ids=standard_ids,
                top_k=top_k,
            )
            if ranked is not None:
                return ranked

            # The index could not answer — missing, empty or built by another encoder. Fall
            # back to substring matching rather than returning nothing, because "no index" and
            # "no relevant clauses" are different answers and only one of them should look
            # like an empty result. `query()` has already logged which it was.
            logger.warning(
                "[retrieval] standards index unusable; falling back to MongoDB substring "
                "matching for this audit. Results will be worse, not absent."
            )
            return await AuditOrchestrator._retrieve_via_substring(
                unique_keywords, standard_ids, top_k
            )
        except Exception as rag_err:
            # Non-fatal: if retrieval fails, the audit continues without lessons
            logger.warning(f"RAG retrieval query failed (non-fatal, continuing audit): {rag_err}")
            return []

    @staticmethod
    async def _retrieve_via_lexical_index(
        query_text: str,
        standard_ids: list[str],
        top_k: int,
    ) -> list[StandardChunk] | None:
        """Rank via the lexical index. Returns None when the index cannot answer at all.

        `None` and `[]` mean different things here and the distinction is the whole point of
        R1's risk section: `[]` is "the index searched and nothing was relevant", `None` is
        "there was no index to search". Only the second justifies a fallback.
        """
        # The index spans every standard; this audit is scoped to the active ones. Over-fetch
        # so that filtering to `standard_ids` cannot empty the result set just because the
        # global top-k happened to come from standards this audit does not use.
        outcome = retrieval.query(
            query_text,
            collection=retrieval.STANDARDS,
            top_k=max(top_k * 4, top_k),
        )
        if not outcome.answered:
            return None

        active = set(standard_ids)
        ordered_ids = [
            hit.record.id
            for hit in outcome.hits
            if not active or hit.record.metadata.get("standard_id") in active
        ][:top_k]

        if not ordered_ids:
            logger.info("[retrieval] standards index answered with no in-scope clauses.")
            return []

        # Fetch the real documents rather than reconstructing them from index metadata. The
        # deleted code built StandardChunk objects out of vector payloads and filled the gaps
        # with placeholders like `id="vector_chunk"`; a retrieved chunk should be the chunk.
        found = await StandardChunk.find({"_id": {"$in": ordered_ids}}).to_list()
        by_id = {str(chunk.id): chunk for chunk in found}

        # Mongo returns these in arbitrary order; restore the ranking retrieval produced.
        ranked = [by_id[cid] for cid in ordered_ids if cid in by_id]
        logger.info(
            f"[retrieval] standards index: {len(ranked)} clause(s) ranked lexically "
            f"(top score {outcome.hits[0].score:.3f})."
        )
        return ranked

    @staticmethod
    async def _retrieve_via_substring(
        unique_keywords: list[str],
        standard_ids: list[str],
        top_k: int,
    ) -> list[StandardChunk]:
        """Case-insensitive `$regex` OR across keywords — the pre-R1 behaviour, kept as fallback.

        Strictly worse than the lexical index: it cannot rank (Mongo returns whatever it finds
        first), and a keyword either appears verbatim or does not. It is here so that an
        unbuilt index degrades the audit instead of silently removing standards grounding.
        """
        query_filter = {
            "standard_id": {"$in": standard_ids},
            "$or": [{"content": {"$regex": kw, "$options": "i"}} for kw in unique_keywords],
        }
        try:
            matched = await StandardChunk.find(query_filter).limit(top_k).to_list()
            logger.info(f"Standards substring fallback: {len(matched)} matching chunk(s).")
            return matched[:top_k]
        except Exception as mongo_err:
            logger.warning(f"Standard chunk keyword lookup failed: {mongo_err}")
            return []
