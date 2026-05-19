from typing import Any, Dict, List
from ....logger import logger

class RemediationEngine:
    """
    Provides actionable, step-by-step suggestions to fix CAD compliance violations.
    """
    
    @staticmethod
    def suggest_fixes(violation: Any) -> List[Dict[str, str]]:
        """
        Returns an ordered list of recommendations to resolve the violation.
        """
        logger.debug(f"Generating remediation for {getattr(violation, 'category', 'unknown')}")
        
        category = getattr(violation, 'category', '')
        suggestions = []
        
        if category == "missing_dimensions":
            suggestions.append({"step": 1, "action": "Add linear dimension connecting geometry endpoints."})
            suggestions.append({"step": 2, "action": "Verify overall bounds match assembly requirements."})
        elif category == "unauthorized_layer":
            suggestions.append({"step": 1, "action": "Select the offending geometry."})
            suggestions.append({"step": 2, "action": "Move entity to an approved production layer (e.g., '0' or 'AM_VIEWS')."})
        else:
            suggestions.append({"step": 1, "action": "Review geometry against standard."})
            
        return suggestions
