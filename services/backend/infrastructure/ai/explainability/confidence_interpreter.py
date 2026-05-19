class ConfidenceInterpreter:
    """
    Translates AI confidence probabilities into understandable metrics for engineers.
    """
    
    @staticmethod
    def interpret(score_probability: float) -> dict:
        """
        Maps a 0.0-1.0 float to a structured confidence badge.
        """
        if score_probability >= 0.95:
            return {"level": "High", "color": "green", "message": "High certainty of non-compliance."}
        elif score_probability >= 0.70:
            return {"level": "Medium", "color": "yellow", "message": "Probable violation, requires human review."}
        else:
            return {"level": "Low", "color": "red", "message": "Low confidence match, possible false positive."}
