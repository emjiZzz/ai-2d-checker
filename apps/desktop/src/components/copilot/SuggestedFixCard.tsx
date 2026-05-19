import React from 'react';

export const SuggestedFixCard: React.FC = () => {
  return (
    <div className="fix-card">
      <span className="card-label">Suggested Fix</span>
      <ol>
        <li>Select the highlighted shaft shoulder geometry.</li>
        <li>Insert a linear dimension indicating total length.</li>
        <li>Apply standard tolerance ±0.05mm per specification.</li>
      </ol>
      <button>
        Accept Recommendation (Manual Fix Required)
      </button>
    </div>
  );
};
