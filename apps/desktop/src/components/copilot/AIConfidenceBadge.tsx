import React from 'react';

interface AIConfidenceBadgeProps {
  score: number; // 0.0 to 1.0
}

export const AIConfidenceBadge: React.FC<AIConfidenceBadgeProps> = ({ score }) => {
  let confidenceLevel = 'low';
  let label = 'Low Confidence';

  if (score >= 0.9) {
    confidenceLevel = 'high';
    label = 'High Confidence';
  } else if (score >= 0.7) {
    confidenceLevel = 'medium';
    label = 'Medium Confidence';
  }

  return (
    <div className={`ai-confidence-badge ${confidenceLevel}`} title={`AI Certainty: ${(score * 100).toFixed(1)}%`}>
      {label}
    </div>
  );
};
