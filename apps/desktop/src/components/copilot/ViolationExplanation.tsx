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
    <div className="flex flex-col gap-3">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-bold text-red-400 m-0">Missing Dimension</h3>
        <AIConfidenceBadge score={mockExplanation.confidence} />
      </div>
      
      <div className="bg-white/3 border border-white/5 p-3 rounded-lg flex flex-col gap-1.5">
        <p className="text-xs font-semibold text-text-primary m-0">{mockExplanation.summary}</p>
        <p className="text-[11px] text-text-muted italic leading-relaxed m-0">{mockExplanation.detailed_reasoning}</p>
      </div>

      <StandardsReferenceCard />
      <SuggestedFixCard />
    </div>
  );
};
