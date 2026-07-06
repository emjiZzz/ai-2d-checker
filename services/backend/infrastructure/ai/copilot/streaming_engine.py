"""
Copilot streaming engine.

Manages real-time token streaming from the Gemini AI model to the React
frontend via Server-Sent Events (SSE). Implements graceful offline fallback
if the API key is not configured.
"""

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
    Manages Server-Sent Events (SSE) token streaming from the Gemini AI model
    back to the React frontend UI.

    Architecture note: Uses ``client.models.generate_content_stream()`` from the
    ``google.genai`` SDK which returns an async iterable of ``GenerateContentResponse``
    chunks. Each chunk is yielded immediately as it arrives, producing a low-latency
    token stream for the copilot chat interface.
    """

    @staticmethod
    def _get_api_key() -> str | None:
        """Returns the configured Gemini API key or None if absent."""
        key = getattr(settings, "GEMINI_API_KEY", None)
        if not key:
            key = os.environ.get("GEMINI_API_KEY")
        return key or None

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
        Yields text tokens asynchronously from the Gemini AI model.

        Args:
            prompt:             The user's copilot question.
            context:            Drawing metadata and audit findings injected as context.
            system_instruction: System-level behaviour instruction for the model.

        Yields:
            Individual text fragments (tokens) as they stream from the API.
        """
        api_key = StreamingEngine._get_api_key()

        if not api_key or not _GENAI_AVAILABLE:
            logger.warning(
                "Copilot streaming: Gemini API key not configured or google-genai not installed. "
                "Returning offline fallback response."
            )
            offline_msg = (
                "⚠️ AI Copilot is currently offline. "
                "Please configure your GEMINI_API_KEY in the .env file to enable live responses. "
                "The rest of the application (rule-based audit, CAD parsing) continues to work normally."
            )
            for word in offline_msg.split(" "):
                yield word + " "
            return

        logger.info(f"Copilot streaming request initiated. Prompt length: {len(prompt)} chars.")

        try:
            client = genai.Client(api_key=api_key)

            # Combine system instruction, drawing context, and user question
            full_prompt = (
                f"{system_instruction}\n\n"
                f"=== DRAWING CONTEXT ===\n{context}\n\n"
                f"=== ENGINEER QUESTION ===\n{prompt}"
            )

            # Stream tokens using the new SDK's async generator
            async for chunk in await client.aio.models.generate_content_stream(
                model="gemini-2.0-flash",
                contents=full_prompt,
            ):
                token = chunk.text
                if token:
                    yield token

            logger.debug("Copilot token stream completed successfully.")

        except Exception as stream_err:
            logger.error(f"Copilot streaming error: {stream_err}")
            yield "\n\n⚠️ An error occurred while generating the AI response. Please try again."
