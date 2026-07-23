import json
from pathlib import Path
from typing import Optional, Dict, Any
from ...storage.path_resolver import get_storage_root
from ....logger import logger

class ComparisonCacheManager:
    """Manages serialization and invalidation of structured visual drawing comparisons."""

    # Bump this whenever a change to comparison LOGIC (not the input files) could change
    # the output for an already-cached (ref, rev, method) triple: orchestrator/prompt
    # changes, extraction/normalization fixes, BOM override logic, coordinate resolution,
    # etc. Without this, a bug fix silently has no effect for any drawing pair a user
    # already ran a comparison on -- the cache keeps serving the pre-fix result until
    # someone thinks to manually clear it. Content-hash alone (ref_hash/rev_hash) only
    # catches the file changing, not the code that interprets it changing.
    # v3: hybrid_orchestrator.py::_resolve_disputed and _pick_cad_bbox both changed —
    # the crop verifier's `differs` field is now read (previously collected and
    # silently ignored, so every disputed finding fell to CONFLICT even when the
    # verifier reported no real difference), and REMOVED/ADDED findings now get a
    # same-drawing fallback crop instead of no crop at all. Existing cached "hybrid"
    # results reflect the old, wrong resolution logic and must not be served as-is.
    # rag/rag_ai/ai_vision are unaffected by this change but share the version lever;
    # their cached entries are also byte-identical to what today's code would produce
    # anyway, so the extra invalidation is harmless, not just unavoidable.
    # v4: this time all four methods genuinely change output for the same inputs.
    # orchestrator.py::generate_deterministic_candidates now excludes entities whose
    # text matches an already-extracted title-block/BOM value (previously these could
    # leak into drawing_views/notes_section/isometric_view as duplicate, wrongly-
    # categorized findings) — affects `rag` directly and hybrid's Generator A.
    # full_ai_orchestrator.py's shared system instruction (build_full_system_
    # instruction) gained explicit categorization-discipline and value-not-label
    # marking rules — affects `rag_ai`/`ai_vision` directly and hybrid's Generator B.
    COMPARISON_CACHE_VERSION = "v4"

    @staticmethod
    def _get_cache_path(
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        method: str = "rag"
    ) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: gemini_comparison_{version}_{method}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json
        # `method` distinguishes rag vs rag_ai results for the same drawing pair so
        # switching a room's comparison_method can't silently serve the other method's cached output.
        # This aligns with api/routers/drawings.py cache invalidation glob/string check, which only
        # substring-matches on drawing_id and doesn't care about the extra segments.
        version = ComparisonCacheManager.COMPARISON_CACHE_VERSION
        filename = f"gemini_comparison_{version}_{method}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_comparison(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        method: str = "rag"
    ) -> Optional[Dict[str, Any]]:
        """Retrieves comparison payload if a valid cache hit exists."""
        cache_file = cls._get_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, method)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Comparison cache hit ({method}) for reference {ref_drawing_id} and revision {rev_drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read comparison cache: {e}")
        return None

    @classmethod
    def set_cached_comparison(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        payload: Dict[str, Any],
        method: str = "rag"
    ) -> None:
        """Saves comparison payload to cache."""
        cache_file = cls._get_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, method)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Comparison cache stored ({method}) at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write comparison cache: {e}")

    # Separate version lever from COMPARISON_CACHE_VERSION on purpose (docs/hybrid-
    # comparison-engine-implementation-plan.md, Phase 7): a change to reconciliation or
    # crop-verifier logic invalidates the *final* hybrid result but not what either
    # generator itself produced, and vice versa for a change to one generator's own
    # diffing/prompt logic. Bumping COMPARISON_CACHE_VERSION forces every method
    # (rag/rag_ai/ai_vision/hybrid) to recompute; bumping this only forces hybrid's
    # generator step to recompute, leaving a still-valid final-result cache entry alone
    # until reconciliation logic changes too.
    # v2: both generators' own output changed (see COMPARISON_CACHE_VERSION v4's note)
    # — Generator A's entity filtering and Generator B's system instruction both
    # changed, so cached hybrid_gen_a/hybrid_gen_b candidates from before this fix no
    # longer reflect what the current code would produce.
    CANDIDATE_CACHE_VERSION = "v2"

    @staticmethod
    def _get_candidate_cache_path(
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        generator: str,
    ) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: hybrid_candidates_{version}_{generator}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json
        # `generator` is "hybrid_gen_a" or "hybrid_gen_b" — kept separate rather than
        # unified with rag's own cache entry (which stores a differently-shaped final
        # PhysicalComparisonResponse, not a raw candidate list) to avoid coupling
        # hybrid's cache format to rag's; noted as a possible future consolidation,
        # not forced here (see Phase 7 completion log).
        version = ComparisonCacheManager.CANDIDATE_CACHE_VERSION
        filename = f"hybrid_candidates_{version}_{generator}_{ref_drawing_id}_{rev_drawing_id}_{ref_hash}_{rev_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_candidates(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        generator: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves one hybrid generator's cached candidate-stage output (pre-reconciliation)."""
        cache_file = cls._get_candidate_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, generator)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Hybrid candidate cache hit ({generator}) for reference {ref_drawing_id} and revision {rev_drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read hybrid candidate cache: {e}")
        return None

    @classmethod
    def set_cached_candidates(
        cls,
        ref_drawing_id: str,
        rev_drawing_id: str,
        ref_hash: str,
        rev_hash: str,
        generator: str,
        payload: Dict[str, Any],
    ) -> None:
        """Stores one hybrid generator's candidate-stage output (pre-reconciliation)."""
        cache_file = cls._get_candidate_cache_path(ref_drawing_id, rev_drawing_id, ref_hash, rev_hash, generator)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Hybrid candidate cache stored ({generator}) at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write hybrid candidate cache: {e}")

    OCR_CACHE_VERSION = "v1"

    @staticmethod
    def _get_ocr_cache_path(drawing_id: str, file_hash: str) -> Path:
        cache_dir = get_storage_root() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Naming format: title_block_ocr_{OCR_CACHE_VERSION}_{drawing_id}_{file_hash}.json
        filename = f"title_block_ocr_{ComparisonCacheManager.OCR_CACHE_VERSION}_{drawing_id}_{file_hash}.json"
        return cache_dir / filename

    @classmethod
    def get_cached_ocr(cls, drawing_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieves single-drawing OCR key-value payloads if cache exists."""
        cache_file = cls._get_ocr_cache_path(drawing_id, file_hash)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                logger.info(f"Title block OCR cache hit for drawing {drawing_id}")
                return payload
            except Exception as e:
                logger.error(f"Failed to read title block OCR cache: {e}")
        return None

    @classmethod
    def set_cached_ocr(cls, drawing_id: str, file_hash: str, payload: Dict[str, Any]) -> None:
        """Stores single-drawing OCR findings to cache."""
        cache_file = cls._get_ocr_cache_path(drawing_id, file_hash)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"Title block OCR cache stored at: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to write title block OCR cache: {e}")

    @classmethod
    def clear_cache_for_drawing(cls, drawing_id: str) -> None:
        """Removes all cache files associated with a specific drawing."""
        cache_dir = get_storage_root() / "cache"
        if not cache_dir.exists():
            return
            
        count = 0
        try:
            for cache_file in cache_dir.glob("*.json"):
                if drawing_id in cache_file.name:
                    cache_file.unlink()
                    count += 1
            if count > 0:
                logger.info(f"Cleared {count} cache files for drawing {drawing_id}")
        except Exception as e:
            logger.error(f"Failed to clear cache for drawing {drawing_id}: {e}")
