import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from domain.models.audit_feedback import AuditFeedbackDocument
from infrastructure.audit.comparison.few_shot_retriever import FewShotRetriever
from infrastructure.audit.comparison.full_ai.prompt_builder import build_full_system_instruction

@pytest.mark.asyncio
async def test_few_shot_retriever_formatting():
    """Verify FewShotRetriever formats AuditFeedbackDocument items into LLM system prompt directives."""
    fb1 = AuditFeedbackDocument.model_construct(
        session_id="s1",
        drawing_id="d1",
        client_name="KMTI",
        entity_text="12.5S",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="dismissed",
    )
    fb2 = AuditFeedbackDocument.model_construct(
        session_id="s2",
        drawing_id="d2",
        client_name="KMTI",
        entity_text="Unit No.",
        category="title_block",
        original_status="CHANGED",
        human_corrected_status="category_override",
    )

    with patch.object(FewShotRetriever, "get_client_exemplars", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [fb1, fb2]

        formatted = await FewShotRetriever.format_exemplars_for_system_instruction("KMTI")
        assert "CLIENT-SPECIFIC HUMAN FEEDBACK EXEMPLARS (Client: KMTI)" in formatted
        assert "12.5S" in formatted
        assert "Unit No." in formatted

@pytest.mark.asyncio
async def test_prompt_builder_few_shot_injection():
    """Verify build_full_system_instruction incorporates few-shot text when client_name is supplied."""
    with patch("infrastructure.audit.comparison.few_shot_retriever.FewShotRetriever.format_exemplars_for_system_instruction", new_callable=AsyncMock) as mock_fmt:
        mock_fmt.return_value = "### EXEMPLARS FOR KMTI:\n- Ignore 12.5S\n"

        prompt = await build_full_system_instruction(client_name="KMTI")
        assert "EXEMPLARS FOR KMTI" in prompt
        assert "Ignore 12.5S" in prompt
