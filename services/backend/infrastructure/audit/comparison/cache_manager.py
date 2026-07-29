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
    # v7: Added MAP, Part No. anchors to title_upper_left in zone_detector.py to exclude top-left administrative table (45 | 2A0 | 4 | 0) from drawing_views.
    # v8: zone_detector._expand_bbox now clamps the padded box back inside max_w/max_h.
    # Padding was previously applied *after* the growth loop returned, so every
    # content-aware zone came out up to 2*BBOX_PADDING oversized in each axis and
    # ZONE_MAX_LIMITS were not actually limits (measured: `title` at 39.1% of sheet height
    # against a declared 35% ceiling). Zone geometry changed on every drawing in the corpus
    # -- mean area fell 22.9%->17.4% for `title`, 27.8%->13.8% for `notes` -- and those boxes
    # feed BOM row extraction, category assignment in result_parser, safe-zone exclusion and
    # crop-verifier tiles. Every cached comparison therefore predates the corrected geometry.
    # v9: hand-aligned zone templates now actually apply. The resolver previously failed to
    # import (relative path one level too shallow) and the caller swallowed it, so every v8
    # entry was computed with detection only. It also lacked the CAD Y flip, which would have
    # mirrored every pinned zone, and converted fractions against the detected geometry frame
    # rather than render_bounds. All three are fixed and templates are wired into all four
    # orchestrators, so v8 results do not reflect any pinned zone.
    # v10: ELLIPSE and SPLINE are now ingested (entity_mapper.map_any had no branch for
    # either and returned None, so both were dropped at extraction -- 111 ellipses and 46
    # splines across the 6-drawing corpus, every one of them on a drawing carrying an
    # isometric view; 38 of the 42 entities in one such view). Two things change for any
    # cached pair: the comparison engine now sees geometry it was previously blind to, so
    # those features can be reported as ADDED/REMOVED/CHANGED for the first time, and
    # zone_detector now resolves `iso` geometrically from ellipse density instead of
    # falling back to a percentage-grid guess on every drawing. That moves the `iso` box
    # and, because `views` is derived by exclusion, the `views` box with it.
    # v11: `views` became templatable, and a pinned `bom` now grows against a content-aware
    # detection instead of overwriting it. Both change zone geometry. The bom overwrite was
    # actively lossy -- a template aligned on a one-row BOM clipped the extra rows off any
    # later drawing, dropping them from BOM extraction silently -- so cached results for any
    # pair using a pinned template can be missing BOM rows entirely. Pinned `views` also
    # changes sub-view clustering and drawing_views coordinate resolution, both of which now
    # subtract the sibling zones via zone_detector.views_exclusions().
    # v12: SpatialDiffer matches in a normalized frame (each drawing's own render_bounds)
    # instead of raw CAD units. The two sides of a comparison are not necessarily in the same
    # coordinate space -- a DXF without a paper-space viewport stays in model units while one
    # with a viewport is projected to paper units. Measured on the M7452A0N01 pair that is a
    # 2.500x scale difference, and since the old pre-alignment estimated a translation only,
    # unchanged title-block text was emitted as REMOVED on one side and ADDED on the other.
    # Every cached result for a pair whose two drawings differ in scale contains those false
    # findings, so all of them predate a correct diff.
    # v13: unambiguous REMOVED/ADDED pairs of identical text are collapsed into a single
    # MATCHED finding (marking_reconciler). The zone partition is computed independently for
    # each drawing, so the same line of text can fall inside the notes box on one side and
    # outside it on the other; it is then diffed against two pools that cannot contain it and
    # reported twice. Measured on the M7452A0N01 pair, 21 of 38 findings were ADDED/REMOVED
    # and 12 of those were six unchanged items counted twice. Cached results predate the
    # collapse and contain those duplicates.
    # v14: Shift-JIS characters whose CP932 trail byte is `\`, `{`, `}` or `~` are no longer
    # mutilated by MTEXT markup stripping (utils/text.py::strip_mtext). Markup was being
    # stripped from the byte-preserving string, before transcode_value decodes it, so e.g.
    # 施 (0x8E 0x7B) lost its trail byte to the `{` strip. Confirmed byte-for-byte against
    # the corruption stored in the database: 素材調質施工 -> 素材調質詩H.
    # This changes zone detection as well as text: ZONE_ANCHORS["tolerance"] contains
    # 表示外公差, which was stored as 侮ｦ外公差 and could never match, so the tolerance zone
    # resolved differently. NOTE this is an INGESTION fix -- drawings already extracted still
    # hold the corrupted text and must be re-ingested; the cache bump alone is not enough.
    COMPARISON_CACHE_VERSION = "v14"

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
