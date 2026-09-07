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

  const getBadgeClass = (level: string) => {
    const base = "py-0.5 px-2 rounded text-[10px] font-bold uppercase tracking-wider border inline-block";
    switch (level) {
      case "high": return `${base} bg-emerald-500/15 border-emerald-500/35 text-emerald-400`;
      case "medium": return `${base} bg-amber-500/15 border-amber-500/35 text-amber-400`;
      case "low": return `${base} bg-red-500/15 border-red-500/35 text-red-400`;
      default: return base;
    }
  };

  return (
    <div className={getBadgeClass(confidenceLevel)} title={`AI Certainty: ${(score * 100).toFixed(1)}%`}>
      {label}
    </div>
  );
};
