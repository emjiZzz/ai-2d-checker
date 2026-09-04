import time
import json
import os
import base64
import httpx
from typing import Any
from google import genai
from google.genai import types
from ....logger import logger
from ....config import settings
from ....api.schemas import PhysicalComparisonResponse

def execute_openai_completion(
    api_key: str,
    system_instruction: str,
    contents: list,
    model: str | None = None
) -> tuple[str, str]:
    """
    Executes a multimodal or text completion request using OpenAI API as automatic failover.
    """
    target_model = model or getattr(settings, "OPENAI_MODEL", "gpt-5.4") or "gpt-5.4"
    logger.info(f"[failover] Dispatching request to OpenAI using model: {target_model}")

    user_parts = []
    for part in contents:
        if isinstance(part, str):
            user_parts.append({"type": "text", "text": part})
        elif hasattr(part, "inline_data") and getattr(part, "inline_data", None):
            mime_type = getattr(part.inline_data, "mime_type", "image/png")
            data_bytes = getattr(part.inline_data, "data", b"")
            b64_data = base64.b64encode(data_bytes).decode("utf-8")
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
            })
        elif hasattr(part, "mime_type") and hasattr(part, "data"):
            mime_type = getattr(part, "mime_type", "image/png")
            data_bytes = getattr(part, "data", b"")
            b64_data = base64.b64encode(data_bytes).decode("utf-8")
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
            })

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_parts if user_parts else "Perform analysis and return required JSON response."}
    ]

    payload = {
        "model": target_model,
        "messages": messages,
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }

    with httpx.Client(timeout=120.0) as http_client:
        res = http_client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        res.raise_for_status()
        res_json = res.json()
        content = res_json["choices"][0]["message"]["content"]
        logger.info(f"[failover] OpenAI request succeeded with model: {target_model}")
        return content, f"openai/{target_model}"

def execute_gemini_cascade(
    api_key: str | None,
    system_instruction: str,
    contents: list,
    response_schema: Any = PhysicalComparisonResponse
) -> tuple[str, str]:
    """Executes Gemini content generation cascade with error handling and automatic OpenAI failover."""
    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)

    # 1. Primary Gemini execution loop if API key exists
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        client = genai.Client(api_key=api_key)
        _model_cascade = settings.GEMINI_MODEL_CASCADE
        _last_err = None

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
                return response.text, _model

            except Exception as _model_err:
                _last_err = _model_err
                _err_str = str(_model_err)
                _is_overload = "503" in _err_str or "429" in _err_str or "RESOURCE_EXHAUSTED" in _err_str or "UNAVAILABLE" in _err_str or "overloaded" in _err_str.lower() or "high demand" in _err_str.lower()
                if _is_overload and _attempt < len(_model_cascade) - 1:
                    _backoff = 2 ** (_attempt + 1)
                    logger.warning(f"{_model} is unavailable (503/overload). Waiting {_backoff}s before trying next model...")
                    time.sleep(_backoff)
                    continue

    # 2. Automatic Failover to OpenAI if Gemini fails or is unconfigured
    if openai_key and openai_key != "YOUR_OPENAI_API_KEY_HERE":
        logger.warning("[failover] Gemini unavailable or exhausted. Automatically triggering OpenAI failover...")
        try:
            return execute_openai_completion(openai_key, system_instruction, contents)
        except Exception as _openai_err:
            logger.error(f"[failover] OpenAI failover also failed: {_openai_err}")
            raise _openai_err

    raise RuntimeError("Neither Gemini nor OpenAI models were able to execute successfully.")

def execute_title_block_ocr(
    api_key: str | None,
    images: dict[str, bytes]
) -> dict:
    """
    Sends cropped Title Block images to Gemini with automatic OpenAI OCR failover.
    """
    from pydantic import create_model
    from .title_block_schema import SingleTitleBlockFields
    
    schema_fields = {label: SingleTitleBlockFields for label in images.keys()}
    DynamicResponse = create_model("DynamicTitleBlockResponse", **{k: (v, ...) for k, v in schema_fields.items()})

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

    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)

    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        client = genai.Client(api_key=api_key)
        _model_cascade = [settings.GEMINI_MODEL_FLASH, settings.GEMINI_MODEL_FALLBACK]
        _model_cascade = list(dict.fromkeys(m for m in _model_cascade if m))

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
                return json.loads(response.text)
            except Exception as _model_err:
                _err_str = str(_model_err)
                _is_overload = "503" in _err_str or "429" in _err_str or "RESOURCE_EXHAUSTED" in _err_str or "UNAVAILABLE" in _err_str
                if _is_overload and _attempt < len(_model_cascade) - 1:
                    time.sleep(2 ** (_attempt + 1))
                    continue

    if openai_key and openai_key != "YOUR_OPENAI_API_KEY_HERE":
        logger.warning("[failover] Gemini Title Block OCR failed or unconfigured. Triggering OpenAI OCR failover...")
        text_res, _ = execute_openai_completion(openai_key, system_instruction, contents)
        return json.loads(text_res)

    raise RuntimeError("Title block OCR failed across all available AI providers.")
