from ....logger import logger


class PromptGuardrails:
    """
    Secures the AI Copilot against jailbreaks, prompt injections, and off-topic queries.
    Enforces that conversations remain strictly focused on CAD, compliance, and engineering.
    """
    
    FORBIDDEN_KEYWORDS = [
        "ignore previous instructions",
        "system prompt",
        "you are a helpful assistant",
        "write a poem",
        "how to hack"
    ]

    @staticmethod
    def sanitize_input(user_message: str) -> bool:
        """
        Returns True if the message is safe, False if it violates security constraints.
        """
        lower_msg = user_message.lower()
        for keyword in PromptGuardrails.FORBIDDEN_KEYWORDS:
            if keyword in lower_msg:
                logger.warning(f"Prompt injection attempt blocked. Keyword: '{keyword}'")
                return False
        return True
