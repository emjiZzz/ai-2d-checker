import re
import time
from datetime import UTC, datetime

from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.standard_chunk import StandardChunk
from ...domain.models.standard_document import StandardDocument
from ...logger import logger
from .ai_engine import AIEngine
from .confidence import ConfidenceScorer
from .rule_engine import RuleEngine
from .violation_detector import ViolationDetector
from ..ai.vectorstore.retrieval_engine import RetrievalEngine


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
        """
        Retrieves the most semantically-relevant StandardChunk snippets for this
        drawing by performing keyword matching against the drawing's layer names,
        entity types extracted from ``entity_counts``, and the file name stem.

        This is the MongoDB-backed RAG retrieval stage. It feeds historically-resolved
        grounding chunks into the Gemini context window as "Lessons Learned",
        reducing hallucination and improving compliance specificity.

        Args:
            drawing:      The DrawingDocument being audited.
            standard_ids: List of active standard document IDs to scope the search.
            top_k:        Maximum number of lessons to inject (keeps prompt size bounded).

        Returns:
            List of relevant StandardChunk objects, capped at ``top_k``.
        """
        # Build a set of keyword tokens from the drawing's metadata
        keywords: list[str] = []

        # 1. Layer names are the strongest signal (e.g. "BORDER", "DIMENSION", "GEOMETRY")
        layer_meta = drawing.metadata.get("layers", [])
        if isinstance(layer_meta, list):
            for layer in layer_meta:
                if isinstance(layer, str) and layer.strip():
                    # Normalise: strip AutoCAD prefixes and split by underscore / hyphen
                    parts = re.split(r"[_\-\s]+", layer.upper())
                    keywords.extend(p.lower() for p in parts if len(p) > 2)

        # 2. Entity types from entity_counts (e.g. "line", "dimension", "text", "hatch")
        for entity_type in drawing.entity_counts.keys():
            keywords.append(entity_type.lower())

        # 3. File name stem can hint at part type (e.g. "anchor_bolt", "flange_detail")
        stem_parts = re.split(r"[_\-\s\.]+", drawing.file_name)
        keywords.extend(p.lower() for p in stem_parts if len(p) > 3)

        if not keywords:
            logger.debug("RAG: No keywords extracted from drawing metadata. Skipping lessons retrieval.")
            return []

        # Deduplicate and trim to avoid overly broad MongoDB queries
        unique_keywords = list(dict.fromkeys(keywords))[:20]
        logger.debug(f"RAG: Querying StandardChunks with keywords: {unique_keywords}")

        # Build a MongoDB $or query: match chunks whose content contains any keyword
        # This is a pragmatic full-text substring match. Once LanceDB is fully wired,
        # this will be replaced with semantic vector similarity search.
        keyword_regex_list = [{"content": {"$regex": kw, "$options": "i"}} for kw in unique_keywords]
        query_filter = {
            "standard_id": {"$in": standard_ids},
            "$or": keyword_regex_list
        }

        try:
            matched: list[StandardChunk] = []

            # 1. Fetch semantic matches from our Local Vector Index first! (Primary - Phase 6.1)
            try:
                engine = RetrievalEngine()
                # Query vector database with drawing file name or top keywords
                query_text = f"{drawing.file_name} " + " ".join(unique_keywords[:5])
                vector_matches = engine.query(query_text, top_k=top_k, collection_name="standards_reference")
                logger.info(f"RAG Vector Index: Retrieved {len(vector_matches)} semantic match(es).")

                # Convert vector matches (dict) to StandardChunk models
                for vm in vector_matches:
                    meta = vm.get("metadata", {})
                    matched.append(
                        StandardChunk(
                            id=meta.get("chunk_id", "vector_chunk"),
                            standard_id=meta.get("standard_id", standard_ids[0]),
                            section_header=meta.get("section_header", "Semantic Standard Clause"),
                            content=vm["text"],
                            page_number=meta.get("page_number", 1)
                        )
                    )
            except Exception as vec_err:
                logger.warning(f"RAG vector index query failed (non-fatal, continuing): {vec_err}")

            # 2. MongoDB keyword query fallback (Secondary - Phase 6.1)
            # If we got fewer than top_k semantic results, back-fill using keyword matches
            if len(matched) < top_k:
                remaining_k = top_k - len(matched)
                try:
                    fallback_chunks = await StandardChunk.find(query_filter).limit(remaining_k).to_list()
                    logger.info(f"RAG MongoDB Fallback: Retrieved {len(fallback_chunks)} matching chunk(s).")
                    for fc in fallback_chunks:
                        # Prevent duplicate content
                        if not any(c.content == fc.content for c in matched):
                            matched.append(fc)
                except Exception as mongo_err:
                    logger.warning(f"MongoDB fallback chunk lookup failed: {mongo_err}")

            return matched[:top_k]
        except Exception as rag_err:
            # Non-fatal: if RAG retrieval fails, the audit continues without lessons
            logger.warning(f"RAG retrieval query failed (non-fatal, continuing audit): {rag_err}")
            return []
