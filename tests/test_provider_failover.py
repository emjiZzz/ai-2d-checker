import pytest
from unittest.mock import patch, MagicMock
from services.backend.infrastructure.audit.comparison.gemini_client import execute_gemini_cascade, execute_openai_completion

def test_execute_gemini_cascade_failover_to_openai(monkeypatch):
    """
    Tests that when Gemini models encounter a rate limit/quota failure (429),
    the system automatically triggers OpenAI failover and succeeds cleanly.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "invalid_or_exhausted_key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock_openai_key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")

    # Mock genai Client to simulate Gemini 429 quota exhaustion
    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded for Gemini")

    # Mock OpenAI http call to simulate successful OpenAI response
    mock_openai_res = (
        '{"title_block": {"status": "MATCH"}, "canvas_markings": []}',
        "openai/gpt-5.4"
    )

    with patch("google.genai.Client", return_value=mock_genai_client):
        with patch("services.backend.infrastructure.audit.comparison.gemini_client.execute_openai_completion", return_value=mock_openai_res) as mock_openai_call:
            res_text, model_used = execute_gemini_cascade(
                api_key="invalid_or_exhausted_key",
                system_instruction="Test system instruction",
                contents=["Test prompt content"]
            )

            assert model_used == "openai/gpt-5.4"
            assert "title_block" in res_text
            mock_openai_call.assert_called_once()
