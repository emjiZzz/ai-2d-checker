import asyncio
import random
import time
import json
from dataclasses import dataclass
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, create_model

from ....logger import logger
from ....config import settings

# Raised from 8 (still not derived from measurement — real payload sizes/quality at
# this N haven't been tested, see the summary log in run_crop_verification below for
# how to validate this with real data). Each finding's schema contribution is cheap
# (3 flat fields), so the binding constraint is image payload, not schema complexity —
# 20 findings x 2 crops = 40 small cropped-region PNGs is well under typical inline-
# request payload ceilings. The real soft limit is per-call verdict-quality dilution
# (one call reasoning about 20+ interleaved findings), not a hard API rejection, which
# is why this stops at 20 rather than jumping further — fewer, larger batches directly
# means fewer total Gemini calls competing for the same per-minute rate-limit window,
# which is the actual lever for the "loops through every model" cost problem observed
# on real hybrid runs with many disputed findings.
MAX_BATCH_SIZE = 20

# How many batches run concurrently. Bounded, not unbounded asyncio.gather — Generator
# B is already making its own Gemini call at the same time, and every batch here is a
# separate call too, so an unbounded burst risks tripping every batch's own 429/503
# backoff simultaneously instead of actually finishing faster. Lowered from 3 to 2:
# real hybrid runs showed multiple concurrent batches getting rate-limited on the same
# per-minute FLASH quota bucket at the same instant, all retrying on FALLBACK in
# lockstep — sometimes exhausting FALLBACK too and failing outright (findings dropped
# to CONFLICT instead of getting a real verdict). 2 keeps real parallelism (vs. 1,
# which would reintroduce the blocking-latency problem this file's async rewrite was
# meant to fix) while reducing the odds of a simultaneous rate-limit collision. Still
# an unmeasured starting point, not a derived number.
MAX_CONCURRENT_BATCHES = 2


class VerificationFields(BaseModel):
    differs: bool = Field(
        ..., description="True if the reference and revision crops show an actual visual difference at this location."
    )
    confirms: Literal["A", "B", "neither"] = Field(
        ...,
        description=(
            "Which generator's account matches the crops: 'A' for the deterministic "
            "generator, 'B' for the AI Vision generator, 'neither' if you cannot "
            "confidently confirm either account from the crops alone."
        ),
    )
    reasoning: str = Field(..., description="Brief explanation of what was seen in the crops and why.")


@dataclass
class CropVerificationInput:
    """
    One disputed finding, already cropped. Producing ref_crop/rev_crop is the caller's
    job (image_cropper.crop_region_image against each candidate's CAD bbox) — this module
    only knows how to batch and ask Gemini about crops it's handed, not how to make them.
    """
    finding_id: str
    ref_crop: Optional[bytes]
    rev_crop: Optional[bytes]
    det_status: str
    det_details: str
    ai_status: str
    ai_details: str


def execute_crop_verification(api_key: str, batch: list[CropVerificationInput]) -> dict:
    """
    Sends paired ref/rev crops for a batch of disputed findings to Gemini in a single
    structured call, asking a narrow yes/no-with-reasoning question about each one — the
    same shape as gemini_client.execute_title_block_ocr, not the open-ended comparison
    call (docs/hybrid-comparison-engine-implementation-plan.md, Phase 3, section 1.4):
    this is a bounded verification task over specific locations, not "compare these
    drawings."

    Returns: dict keyed by finding_id -> {"differs": bool, "confirms": "A"|"B"|"neither", "reasoning": str}
    """
    schema_fields = {f.finding_id: VerificationFields for f in batch}
    DynamicResponse = create_model("DynamicCropVerificationResponse", **{k: (v, ...) for k, v in schema_fields.items()})

    client = genai.Client(api_key=api_key)

    contents: list = []
    for f in batch:
        contents.append(
            f"=== FINDING {f.finding_id} ===\n"
            f"Deterministic generator says: {f.det_status} — {f.det_details}\n"
            f"AI Vision generator says: {f.ai_status} — {f.ai_details}\n"
            f"The following image is the REFERENCE drawing, cropped to this finding's location:"
        )
        if f.ref_crop:
            contents.append(types.Part.from_bytes(data=f.ref_crop, mime_type="image/png"))
        else:
            contents.append("(no reference crop available)")

        contents.append("The following image is the REVISION drawing, cropped to the same location:")
        if f.rev_crop:
            contents.append(types.Part.from_bytes(data=f.rev_crop, mime_type="image/png"))
        else:
            contents.append("(no revision crop available)")

    system_instruction = (
        "You are verifying disputed findings between two independent drawing-comparison "
        "generators — one deterministic (reads exact CAD entity data), one AI-vision-based "
        "(reads rendered images). They disagree about specific locations, listed below one "
        "finding at a time. For EACH finding, look only at that finding's own reference/"
        "revision crop pair and decide: do the two crops actually show a difference at all? "
        "Then decide which generator's account matches what you see — 'A' for the "
        "deterministic generator, 'B' for the AI Vision generator, or 'neither' if you "
        "cannot confidently confirm either account from the crops alone. Do not guess — "
        "'neither' is the correct answer when the crops are ambiguous, low-resolution, or "
        "the disputed content isn't visible in the crop. Only return JSON keys for the "
        "finding IDs actually provided."
    )
    contents.append("Verify each disputed finding, structured according to the response schema.")

    # Flash-tier only — same reasoning as execute_title_block_ocr: a bounded
    # verification task over specific locations, not the open-ended reasoning the full
    # comparison pipeline needs.
    _model_cascade = [settings.GEMINI_MODEL_FLASH, settings.GEMINI_MODEL_FALLBACK]
    _model_cascade = list(dict.fromkeys(m for m in _model_cascade if m))
    _last_err = None
    response = None

    for _attempt, _model in enumerate(_model_cascade):
        try:
            logger.info(f"[hybrid/verifier] Crop verification attempt {_attempt + 1}/{len(_model_cascade)} using model: {_model}")
            response = client.models.generate_content(
                model=_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=DynamicResponse,
                    temperature=0.0,
                ),
            )
            logger.info(f"[hybrid/verifier] Crop verification succeeded with model: {_model}")
            break
        except Exception as _model_err:
            _last_err = _model_err
            _err_str = str(_model_err)
            _is_overload = (
                "503" in _err_str or "429" in _err_str or "RESOURCE_EXHAUSTED" in _err_str
                or "UNAVAILABLE" in _err_str or "overloaded" in _err_str.lower() or "high demand" in _err_str.lower()
            )
            if _is_overload and _attempt < len(_model_cascade) - 1:
                # Additive jitter (not full jitter — the base backoff here is already
                # small, only one retry step exists in this 2-tier cascade, and full
                # jitter risks under-sleeping) so concurrent batches rate-limited in the
                # same instant don't all retry on FALLBACK in lockstep and collide again.
                _backoff = 2 ** (_attempt + 1) + random.uniform(0, 1)
                logger.warning(f"{_model} is unavailable. Waiting {_backoff:.1f}s before trying next model...")
                time.sleep(_backoff)
                continue
            raise _model_err

    if response is None:
        raise _last_err or RuntimeError("All Gemini crop verification models failed without a response.")

    return json.loads(response.text)


async def run_crop_verification(api_key: str, inputs: list[CropVerificationInput]) -> dict[str, dict]:
    """
    Chunks `inputs` into batches of MAX_BATCH_SIZE and calls execute_crop_verification
    per batch, merging results into one dict keyed by finding_id.

    Async, running batches concurrently (bounded by MAX_CONCURRENT_BATCHES) via
    asyncio.to_thread — execute_crop_verification is a synchronous, blocking Gemini SDK
    call, same as execute_gemini_cascade/execute_title_block_ocr elsewhere in this
    codebase, which are always dispatched through asyncio.to_thread rather than called
    directly from an async function. This used to be a plain synchronous for-loop
    called directly from perform_hybrid_comparison: with ~8 batches for a real drawing
    pair, that blocked the entire FastAPI event loop — not just this one request — for
    the full sequential duration of every batch, and was the direct cause of the
    frontend's fetch timing out ("signal is aborted without reason") on drawing pairs
    with many disputed findings.

    A failed batch is logged and its findings are simply absent from the result
    (dropped, not defaulted to a fabricated verdict) — the caller
    (hybrid_orchestrator.py) is responsible for treating any finding_id missing from
    the result as unresolved/CONFLICT rather than silently passing it through as
    confirmed.
    """
    batches = [inputs[i:i + MAX_BATCH_SIZE] for i in range(0, len(inputs), MAX_BATCH_SIZE)]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    failed_batch_count = 0

    async def _run_batch(batch: list[CropVerificationInput]) -> dict[str, dict]:
        nonlocal failed_batch_count
        async with semaphore:
            try:
                return await asyncio.to_thread(execute_crop_verification, api_key, batch)
            except Exception as batch_err:
                ids = [f.finding_id for f in batch]
                logger.error(f"[hybrid/verifier] Crop verification batch failed for {ids}: {batch_err}")
                failed_batch_count += 1
                return {}

    _start = time.monotonic()
    batch_results = await asyncio.gather(*(_run_batch(b) for b in batches))
    _elapsed = time.monotonic() - _start

    results: dict[str, dict] = {}
    for br in batch_results:
        results.update(br)

    # Turns the "placeholder, tune later" status of MAX_BATCH_SIZE/MAX_CONCURRENT_BATCHES
    # above into something actually tunable with real data instead of another guess —
    # the verified/submitted delta is exactly how many findings got dropped to CONFLICT
    # because their batch failed outright, which is the number that mattered most when
    # this was diagnosed against a real hybrid run.
    logger.info(
        f"[hybrid/verifier] {len(batches)} batch(es), {len(results)}/{len(inputs)} findings verified, "
        f"{failed_batch_count} batch(es) failed outright, {_elapsed:.1f}s total"
    )
    return results
