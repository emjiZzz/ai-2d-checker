import React from 'react';

export const GeometryInsightPanel: React.FC = () => {
  return (
    <div className="geometry-insight">
      <div className="geometry-insight-card">
        <h3>Detected Patterns</h3>
        <ul>
          <li>
            <span style={{ color: "#10b981", fontWeight: "bold" }}>✓</span>
            Standard Title Block recognized
          </li>
          <li>
            <span style={{ color: "#fbbf24", fontWeight: "bold" }}>⚠</span>
            4 repeated M3 bolt-hole clusters found
          </li>
          <li>
            <span style={{ color: "#3b82f6", fontWeight: "bold" }}>ℹ</span>
            Symmetry identified along Y-axis
          </li>
        </ul>
      </div>

      <div className="geometry-insight-card">
        <h3>Similar Geometry Search</h3>
        <p>Select a primitive to find identical structures across the CAD canvas.</p>
        <button>
          Scan for Matching Vectors
        </button>
      </div>
    </div>
  );
};
