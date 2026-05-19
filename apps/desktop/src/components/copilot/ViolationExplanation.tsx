import React from 'react';
import { StandardsReferenceCard } from './StandardsReferenceCard';
import { SuggestedFixCard } from './SuggestedFixCard';
import { AIConfidenceBadge } from './AIConfidenceBadge';

export const ViolationExplanation: React.FC = () => {
  // Mock data representing the violation reasoner output
  const mockExplanation = {
    summary: "Missing explicit linear dimensioning on load-bearing shaft shoulder.",
    detailed_reasoning: "Machining constraints require all physical geometries to be explicitly dimensioned. This prevents arbitrary shop-floor sizing, which could lead to loose tolerances during assembly.",
    confidence: 0.96
  };

  return (
    <div className="violation-explanation">
      <div className="violation-explanation-header">
        <h3>Missing Dimension</h3>
        <AIConfidenceBadge score={mockExplanation.confidence} />
      </div>
      
      <div className="geometry-insight-card">
        <p style={{ fontSize: "0.85rem", color: "#e2e8f0", fontWeight: 500, marginBottom: "6px" }}>{mockExplanation.summary}</p>
        <p style={{ fontSize: "0.75rem", color: "#94a3b8", fontStyle: "italic", lineHeight: 1.4 }}>{mockExplanation.detailed_reasoning}</p>
      </div>

      <StandardsReferenceCard />
      <SuggestedFixCard />
    </div>
  );
};
