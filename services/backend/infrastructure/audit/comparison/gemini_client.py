import time
import json
from typing import Any
from google import genai
from google.genai import types
from ....logger import logger
from ....config import settings
from ....api.schemas import PhysicalComparisonResponse

def execute_gemini_cascade(
    api_key: str,
    system_instruction: str,
    contents: list,
    response_schema: Any = PhysicalComparisonResponse
) -> tuple[str, str]:
    """Executes Gemini content generation cascade with error handling and fallback logic.

    Returns (response_text, model_used) — the caller needs to know which model in the
    cascade actually produced the result: a mid-run fallback (e.g. Pro -> Flash on
    rate-limit) silently swaps a high-reasoning model for a materially weaker one for
    the same comparison, and previously nothing surfaced which model answered, so two
    runs of the "same" comparison could differ in quality for reasons invisible to
    anyone looking at the result.
    """
    client = genai.Client(api_key=api_key)

    # Driven by config.py's settings.GEMINI_MODEL_CASCADE (env-controlled: GEMINI_MODEL_PRO,
    # GEMINI_MODEL_FLASH, GEMINI_MODEL_FALLBACK) instead of a hardcoded list — Google's
    # Gemini deprecation cadence has been fast enough this year that a hardcoded cascade
    # goes stale within months.
    _model_cascade = settings.GEMINI_MODEL_CASCADE
    _last_err = None
    response = None
    _model_used = None

    for _attempt, _model in enumerate(_model_cascade):
        try:
            logger.info(f"Gemini comparison attempt {_attempt + 1}/{len(_model_cascade)} using model: {_model}")
            response = client.models.generate_content(
                model=_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.0
                )
            )
            logger.info(f"Gemini comparison succeeded with model: {_model}")
            _model_used = _model
            break
        except Exception as _model_err:
            _last_err = _model_err
            _err_str = str(_model_err)
            _is_overload = "503" in _err_str or "429" in _err_str or "RESOURCE_EXHAUSTED" in _err_str or "UNAVAILABLE" in _err_str or "overloaded" in _err_str.lower() or "high demand" in _err_str.lower()
            if _is_overload and _attempt < len(_model_cascade) - 1:
                _backoff = 2 ** (_attempt + 1)
                logger.warning(f"{_model} is unavailable (503/overload). Waiting {_backoff}s before trying next model...")
                time.sleep(_backoff)
                continue
            raise _model_err

    if response is None:
        raise _last_err or RuntimeError("All Gemini models failed without a response.")

    return response.text, _model_used

def execute_title_block_ocr(
    api_key: str,
    images: dict[str, bytes]
) -> dict:
    """
    Sends cropped Title Block images to Gemini in a single batched structured call.
    Uses Pydantic's create_model to dynamically construct the expected JSON schema on the fly
    depending on which images (reference, revision, or both) are missing.
    """
    from pydantic import create_model
    from .title_block_schema import SingleTitleBlockFields
    
    schema_fields = {label: SingleTitleBlockFields for label in images.keys()}
    DynamicResponse = create_model("DynamicTitleBlockResponse", **{k: (v, ...) for k, v in schema_fields.items()})

    client = genai.Client(api_key=api_key)
    
    contents = []
    for label, img_bytes in images.items():
        contents.append(f"The following image is the {label.upper()} drawing's title block:")
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

    system_instruction = (
        "You will be given one or two title block images, each preceded by a label indicating REFERENCE or REVISION.\n"
        "Extract the scale, title, drawing number, drawn by, designed by, and quantity fields from the title block.\n"
        "If a field is not visibly present in the image, return null. Do not infer or guess a value.\n"
        "Only return JSON keys for the labels actually provided."
    )

    task_prompt = "Extract the title block fields structured according to the response schema."
    contents.append(task_prompt)

    # Flash-tier only — this is a bounded structured-extraction task (a handful of
    # labeled fields from a cropped title block image), not the open-ended reasoning
    # the full comparison pipeline needs, so it doesn't warrant the PRO tier's
    # cost/latency. Still env-driven via settings, same reasoning as execute_gemini_cascade.
    _model_cascade = [settings.GEMINI_MODEL_FLASH, settings.GEMINI_MODEL_FALLBACK]
    _model_cascade = list(dict.fromkeys(m for m in _model_cascade if m))  # dedupe, preserve order
    _last_err = None
    response = None
    
    for _attempt, _model in enumerate(_model_cascade):
        try:
            logger.info(f"Gemini title block OCR attempt {_attempt + 1}/{len(_model_cascade)} using model: {_model}")
            response = client.models.generate_content(
                model=_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=DynamicResponse,
                    temperature=0.0
                )
            )
            logger.info(f"Gemini title block OCR succeeded with model: {_model}")
            break
        except Exception as _model_err:
            _last_err = _model_err
            _err_str = str(_model_err)
            _is_overload = "503" in _err_str or "429" in _err_str or "RESOURCE_EXHAUSTED" in _err_str or "UNAVAILABLE" in _err_str or "overloaded" in _err_str.lower() or "high demand" in _err_str.lower()
            if _is_overload and _attempt < len(_model_cascade) - 1:
                _backoff = 2 ** (_attempt + 1)
                logger.warning(f"{_model} is unavailable. Waiting {_backoff}s before trying next model...")
                time.sleep(_backoff)
                continue
            raise _model_err
            
    if response is None:
        raise _last_err or RuntimeError("All Gemini OCR models failed without a response.")
        
    return json.loads(response.text)
