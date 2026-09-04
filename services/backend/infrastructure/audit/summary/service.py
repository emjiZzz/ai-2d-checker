"""Orchestration: cache -> generate -> verify -> outcome. ADR-010 decisions 3, 4 and 6.

The order matters and is asserted by test. Verification runs before anything is cached, so a
summary that failed the gate can never be served from cache later.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ....config import settings
from ....logger import logger
from ...storage.path_resolver import get_storage_root
from .generate import SummaryUnavailableError, deterministic_summary, generate
from .models import (
    Finding,
    GroundedSummary,
    SummaryOutcome,
    SummaryStatus,
)
from .verify import verify

# Bumped when the prompt, the schema or the verification rules change -- i.e. when a cached
# summary would no longer be the output this code produces.
#
# Deliberately NOT COMPARISON_CACHE_VERSION (ADR-010 decision 6, CLAUDE.md constraint 2). Sharing
# that lever would mean a prompt reword invalidates real comparisons, and would quietly widen a
# constraint written for spatial matching and zone extraction into "anything AI-adjacent".
SUMMARY_CACHE_VERSION = 1


def finding_digest(findings: list[Finding]) -> str:
    """The cache key. A summary is a pure function of the finding list, so the list is the key.

    Sorted by id so that a reordering of the same findings is a cache hit rather than a
    regeneration -- the summary of a set does not depend on the order the set arrived in.
    """
    payload = json.dumps(
        [
            {"id": f.id, "category": f.category, "status": f.status, "description": f.description}
            for f in sorted(findings, key=lambda f: f.id)
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _cache_path(digest: str) -> Path:
    root = Path(get_storage_root()) / "cache" / "summaries"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"v{SUMMARY_CACHE_VERSION}_{digest}.json"


def _read_cache(digest: str) -> GroundedSummary | None:
    path = _cache_path(digest)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return GroundedSummary.model_validate(raw["summary"])
    except (OSError, ValueError, KeyError) as err:
        # A corrupt cache entry is not a reason to fail the request; regenerate. Narrow catch on
        # purpose -- an AttributeError here should crash, per the lesson in
        # Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op.
        logger.warning(f"[summary] Discarding unreadable cache entry {path.name}: {err}")
        return None


def _write_cache(digest: str, summary: GroundedSummary, model_used: str) -> None:
    try:
        _cache_path(digest).write_text(
            json.dumps(
                {"summary": summary.model_dump(), "model_used": model_used},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as err:
        logger.warning(f"[summary] Could not cache summary {digest}: {err}")


def summarize(findings: list[Finding], *, language: str | None = None) -> SummaryOutcome:
    """Produce a verified summary, or say precisely why there isn't one.

    Never raises for an absent summary. Every return path carries `fallback_text`, so a caller
    always has something truthful to render -- ADR-010 decision 4.
    """
    fallback = deterministic_summary(findings)
    base = {"fallback_text": fallback, "finding_count": len(findings)}

    if not findings:
        return SummaryOutcome(status=SummaryStatus.NOT_APPLICABLE, **base)

    if not settings.ENABLE_LLM_SUMMARY:
        return SummaryOutcome(status=SummaryStatus.DISABLED, **base)

    digest = finding_digest(findings)
    cached = _read_cache(digest)
    if cached is not None:
        # Re-verify on read rather than trusting the cache. Cheap, and it means a change to the
        # verification rules takes effect on already-cached summaries instead of grandfathering
        # output that today's gate would reject.
        result = verify(cached, findings)
        if result.ok:
            return SummaryOutcome(
                status=SummaryStatus.OK,
                headline=cached.headline,
                claims=cached.claims,
                cached=True,
                **base,
            )
        logger.warning(f"[summary] Cached summary {digest} no longer verifies; regenerating.")

    try:
        summary, model_used = generate(findings, language or "English")
    except SummaryUnavailableError as err:
        logger.info(f"[summary] Unavailable: {err}")
        return SummaryOutcome(status=SummaryStatus.UNAVAILABLE, **base)

    result = verify(summary, findings)
    if not result.ok:
        # Withheld, whole. Not truncated to the part that verified, and not retried -- see the
        # module docstring in verify.py.
        logger.warning(
            f"[summary] Withheld a generated summary: {[f.value for f in result.failures]} "
            f"-- {result.detail}"
        )
        return SummaryOutcome(
            status=SummaryStatus.WITHHELD,
            withheld_reasons=result.failures,
            withheld_detail=result.detail,
            model_used=model_used,
            **base,
        )

    _write_cache(digest, summary, model_used)
    return SummaryOutcome(
        status=SummaryStatus.OK,
        headline=summary.headline,
        claims=summary.claims,
        model_used=model_used,
        **base,
    )
