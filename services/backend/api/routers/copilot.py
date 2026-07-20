from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ...logger import logger
from ..dependencies import get_auth_token

router = APIRouter()


class CopilotStreamRequest(BaseModel):
    message: str
    context: str = ""
    history: list[dict] = []


@router.post(
    "/copilot/stream",
    summary="Stream AI Copilot token response via Server-Sent Events",
    dependencies=[Depends(get_auth_token)]
)
async def copilot_stream(body: CopilotStreamRequest):
    """
    Streams real-time token-by-token responses from the configured Gemini Flash-tier
    model (settings.GEMINI_MODEL_FLASH, see config.py) to the React Copilot panel via
    SSE. Accepts conversation history for multi-turn context.
    Includes offline fallback if the API key is not configured.
    """
    from ...infrastructure.ai.copilot.streaming_engine import StreamingEngine

    # Reconstruct conversational history as prefix context
    history_text = ""
    for turn in body.history[-10:]:  # Limit context window to last 10 turns
        role = str(turn.get("role", "user")).upper()
        content = str(turn.get("content", ""))
        history_text += f"\n[{role}]: {content}"

    full_prompt = f"{history_text}\n[USER]: {body.message}".strip()

    async def sse_generator():
        try:
            async for token in StreamingEngine.generate_token_stream(
                prompt=full_prompt,
                context=body.context
            ):
                # SSE format: each message must be prefixed with 'data: ' and end with double newline
                yield f"data: {token}\n\n"
        except Exception as gen_err:
            logger.error(f"Copilot SSE stream generator error: {gen_err}")
            yield "data: ⚠️ An error occurred while generating the response.\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx proxy buffering for SSE
            "Connection": "keep-alive"
        }
    )
