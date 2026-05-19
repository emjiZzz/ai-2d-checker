from typing import Any, Dict
from ....logger import logger

class ViolationReasoner:
    """
    Analyzes raw audit violations and synthesizes human-readable engineering explanations.
    """
    
    @staticmethod
    def generate_explanation(violation: Any) -> Dict[str, str]:
        """
        Derives the 'WHY' behind a CAD compliance violation.
        """
        logger.info(f"Generating reasoning for violation {getattr(violation, 'id', 'unknown')}")
        
        # In production, this would leverage local RAG context or predefined deterministic heuristics.
        reasoning = "The specified geometry conflicts with production engineering standards."
        if getattr(violation, 'category', '') == "missing_dimensions":
            reasoning = "Machining constraints require all physical geometries to be explicitly dimensioned to prevent arbitrary shop-floor sizing."
            
        return {
            "summary": getattr(violation, "description", "Unknown violation"),
            "detailed_reasoning": reasoning,
            "impact": "High manufacturing defect risk if uncorrected."
        }
