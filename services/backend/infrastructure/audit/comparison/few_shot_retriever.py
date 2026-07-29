"""
Dynamic Few-Shot RAG Exemplar Memory Retriever (Pillar 4).

Queries historical human feedback events (AuditFeedbackDocument) from MongoDB
and dynamically formats client-specific few-shot exemplars to inject into
Gemini system prompts (prompt_builder.py).
"""

from typing import List, Optional
try:
    from ....domain.models.audit_feedback import AuditFeedbackDocument
    from ....logger import logger
except Exception:
    from domain.models.audit_feedback import AuditFeedbackDocument
    try:
        from logger import logger
    except Exception:
        import logging
        logger = logging.getLogger("few_shot_retriever")

class FewShotRetriever:
    """Retrieves and formats historical human feedback into LLM system prompt directives."""

    @staticmethod
    async def get_client_exemplars(client_name: Optional[str], limit: int = 5) -> List[AuditFeedbackDocument]:
        """Queries historical human feedback events for the given client_name."""
        if not client_name:
            return []
        try:
            feedbacks = await AuditFeedbackDocument.find(
                AuditFeedbackDocument.client_name == client_name
            ).sort("-created_at").limit(limit).to_list()
            return feedbacks
        except Exception as err:
            logger.warning(f"[few_shot_retriever] Failed to query feedback for client '{client_name}': {err}")
            return []

    @classmethod
    async def format_exemplars_for_system_instruction(cls, client_name: Optional[str]) -> str:
        """Formats historical human feedback into few-shot directives for system prompts."""
        if not client_name:
            return ""

        feedbacks = await cls.get_client_exemplars(client_name, limit=5)
        if not feedbacks:
            return ""

        lines = [
            f"\n### CLIENT-SPECIFIC HUMAN FEEDBACK EXEMPLARS (Client: {client_name}):",
            "Follow these verified human engineer feedback directives for this client family:"
        ]

        for fb in feedbacks:
            if fb.human_corrected_status == "dismissed":
                lines.append(
                    f"- [HUMAN OVERRIDE - IGNORE PATTERN]: Pattern '{fb.entity_text}' in category '{fb.category}' "
                    f"was explicitly DISMISSED by human engineers. Do NOT report '{fb.entity_text}' as a discrepancy."
                )
            elif fb.human_corrected_status == "category_override":
                lines.append(
                    f"- [HUMAN OVERRIDE - CATEGORY RE-ASSIGNMENT]: Pattern '{fb.entity_text}' belongs to category "
                    f"'{fb.category}', not other categories."
                )
            elif fb.human_corrected_status == "confirmed_valid":
                lines.append(
                    f"- [HUMAN CONFIRMED]: Pattern '{fb.entity_text}' in category '{fb.category}' "
                    f"was explicitly CONFIRMED as a critical discrepancy by engineers."
                )

        return "\n".join(lines) + "\n"
