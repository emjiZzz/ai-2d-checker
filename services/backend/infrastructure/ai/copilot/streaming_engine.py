"""
Copilot streaming engine.

Manages real-time token streaming from the Gemini AI model to the React
frontend via Server-Sent Events (SSE). Implements graceful offline fallback
if the API key is not configured.
"""

import json
import os
from collections.abc import AsyncGenerator

from ....config import settings
from ....logger import logger

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None           # type: ignore
    genai_types = None     # type: ignore
    _GENAI_AVAILABLE = False


class StreamingEngine:
    """
    Manages Server-Sent Events (SSE) token streaming from the Gemini or OpenAI AI model
    back to the React frontend UI.
    """

    @staticmethod
    def _get_api_key() -> str | None:
        """Returns the configured Gemini API key or None if absent."""
        key = getattr(settings, "GEMINI_API_KEY", None)
        if not key:
            key = os.environ.get("GEMINI_API_KEY")
        if key and key != "YOUR_GEMINI_API_KEY_HERE":
            return key.strip()
        return None

    @staticmethod
    def _get_openai_api_key() -> str | None:
        """Returns the configured OpenAI API key or None if absent."""
        key = getattr(settings, "OPENAI_API_KEY", None)
        if not key:
            key = os.environ.get("OPENAI_API_KEY")
        if key and key != "YOUR_OPENAI_API_KEY_HERE":
            return key.strip()
        return None

    @staticmethod
    async def _stream_openai(
        prompt: str,
        context: str,
        system_instruction: str,
        api_key: str
    ) -> AsyncGenerator[str, None]:
        """Streams token-by-token responses from OpenAI Chat Completions API."""
        import httpx
        target_model = getattr(settings, "OPENAI_MODEL", "gpt-5.4") or "gpt-4o"
        logger.info(f"[failover] Streaming Copilot from OpenAI using model: {target_model}")

        messages = [
            {
                "role": "system",
                "content": (
                    f"{system_instruction}\n\n"
                    f"=== DRAWING CONTEXT ===\n{context}"
                )
            },
            {"role": "user", "content": prompt}
        ]

        payload = {
            "model": target_model,
            "messages": messages,
            "stream": True,
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            async with http_client.stream("POST", "https://api.openai.com/v1/chat/completions", json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            delta = data_json.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content")
                            if token:
                                yield token
                        except Exception:
                            continue

    @staticmethod
    async def generate_token_stream(
        prompt: str,
        context: str,
        system_instruction: str = (
            "You are an expert engineering drawing compliance assistant. "
            "Answer clearly, concisely, and grounded in the provided drawing context. "
            "When referencing standards always cite the clause or section number."
        )
    ) -> AsyncGenerator[str, None]:
        """
        Yields text tokens asynchronously from Gemini with automatic OpenAI fallback.

        Args:
            prompt:             The user's copilot question.
            context:            Drawing metadata and audit findings injected as context.
            system_instruction: System-level behaviour instruction for the model.

        Yields:
            Individual text fragments (tokens) as they stream from the API.
        """
        gemini_key = StreamingEngine._get_api_key()
        openai_key = StreamingEngine._get_openai_api_key()

        if not gemini_key and not openai_key:
            logger.warning(
                "Copilot streaming: Neither Gemini nor OpenAI API key is configured. "
                "Returning offline fallback response."
            )
            offline_msg = (
                "⚠️ AI Copilot is currently offline. "
                "Please configure your GEMINI_API_KEY or OPENAI_API_KEY in the .env file to enable live responses."
            )
            for word in offline_msg.split(" "):
                yield word + " "
            return

        # 1. Try Gemini first if configured and available
        if gemini_key and _GENAI_AVAILABLE and genai is not None:
            logger.info(f"Copilot streaming request initiated with Gemini. Prompt length: {len(prompt)} chars.")
            try:
                client = genai.Client(api_key=gemini_key)
                full_prompt = (
                    f"{system_instruction}\n\n"
                    f"=== DRAWING CONTEXT ===\n{context}\n\n"
                    f"=== ENGINEER QUESTION ===\n{prompt}"
                )

                primary_model = settings.GEMINI_MODEL_FLASH
                fallback_model = settings.GEMINI_MODEL_FALLBACK
                models_to_try = [primary_model] if primary_model == fallback_model else [primary_model, fallback_model]

                stream = None
                last_err: Exception | None = None
                for attempt, model_name in enumerate(models_to_try):
                    try:
                        stream = await client.aio.models.generate_content_stream(
                            model=model_name,
                            contents=full_prompt,
                        )
                        if attempt > 0:
                            logger.warning(f"Copilot streaming: primary model '{primary_model}' failed, succeeded on fallback '{model_name}'.")
                        break
                    except Exception as model_err:
                        last_err = model_err
                        logger.warning(f"Copilot streaming: Gemini model '{model_name}' failed ({model_err}).")
                        continue

                if stream is not None:
                    async for chunk in stream:
                        token = chunk.text
                        if token:
                            yield token
                    logger.debug("Copilot Gemini token stream completed successfully.")
                    return
                else:
                    logger.warning(f"All Gemini models exhausted ({last_err}). Falling back to OpenAI if available...")

            except Exception as stream_err:
                logger.warning(f"Copilot Gemini error: {stream_err}. Attempting OpenAI failover...")

        # 2. Automatic Failover to OpenAI
        if openai_key:
            try:
                async for token in StreamingEngine._stream_openai(
                    prompt=prompt,
                    context=context,
                    system_instruction=system_instruction,
                    api_key=openai_key
                ):
                    yield token
                logger.debug("Copilot OpenAI token stream completed successfully.")
                return
            except Exception as openai_err:
                logger.error(f"Copilot OpenAI streaming failed: {openai_err}")
                yield f"\n\n⚠️ OpenAI Copilot streaming error: {openai_err}"
                return

        yield "\n\n⚠️ An error occurred while generating the AI response. Please check your API quota or keys."

