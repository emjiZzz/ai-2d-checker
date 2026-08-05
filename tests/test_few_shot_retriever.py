"""Stage 0g — relocated from `services/backend/tests/test_few_shot_retriever.py`, which had
**never executed** (outside `testpaths`, and its `infrastructure.*` imports fail collection
from the repo root).

Worth knowing what these tests do and do not establish. `FewShotRetriever` is
`find(client_name).sort("-created_at").limit(5)` — a recency filter with no query and no
similarity, and it feeds only the Gemini system prompt, which the default `rag` method never
invokes. See [[00 - AI Maturity Status]]. So these pin **formatting and wiring**, not
retrieval quality; there is no retrieval to have quality. Stage 1 replaces the ranking and
must keep `format_exemplars_for_system_instruction`'s output contract, which is exactly what
the first test here holds still.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.backend.domain.models.audit_feedback import AuditFeedbackDocument
from services.backend.infrastructure.audit.comparison.few_shot_retriever import FewShotRetriever
from services.backend.infrastructure.audit.comparison.full_ai.prompt_builder import (
    build_full_system_instruction,
)


@pytest.mark.asyncio
async def test_exemplars_are_formatted_into_system_prompt_directives():
    dismissed = AuditFeedbackDocument.model_construct(
        session_id="s1",
        drawing_id="d1",
        client_name="KMTI",
        entity_text="12.5S",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="dismissed",
    )
    recategorised = AuditFeedbackDocument.model_construct(
        session_id="s2",
        drawing_id="d2",
        client_name="KMTI",
        entity_text="Unit No.",
        category="title_block",
        original_status="CHANGED",
        human_corrected_status="category_override",
    )

    with patch.object(
        FewShotRetriever, "get_client_exemplars", new_callable=AsyncMock
    ) as get_exemplars:
        get_exemplars.return_value = [dismissed, recategorised]
        formatted = await FewShotRetriever.format_exemplars_for_system_instruction("KMTI")

    assert "CLIENT-SPECIFIC HUMAN FEEDBACK EXEMPLARS (Client: KMTI)" in formatted
    assert "12.5S" in formatted
    assert "Unit No." in formatted


@pytest.mark.asyncio
async def test_prompt_builder_injects_the_exemplar_block_when_a_client_is_named():
    """`prompt_builder` reads the retriever's formatted output verbatim. Stage 1 rewrites
    what goes *into* that string but must not change the seam, or every prompt changes with
    it."""
    target = (
        "services.backend.infrastructure.audit.comparison.few_shot_retriever"
        ".FewShotRetriever.format_exemplars_for_system_instruction"
    )
    with patch(target, new_callable=AsyncMock) as formatter:
        formatter.return_value = "### EXEMPLARS FOR KMTI:\n- Ignore 12.5S\n"
        prompt = await build_full_system_instruction(client_name="KMTI")

    assert "EXEMPLARS FOR KMTI" in prompt
    assert "Ignore 12.5S" in prompt
