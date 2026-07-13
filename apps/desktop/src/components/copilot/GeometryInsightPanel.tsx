import React from 'react';

export const GeometryInsightPanel: React.FC = () => {
  return (
    <div className="flex flex-col gap-3">
      <div className="bg-white/3 border border-white/5 p-3 rounded-lg flex flex-col gap-2">
        <h3 className="text-xs font-bold text-blue-400 m-0">Detected Patterns</h3>
        <ul className="flex flex-col gap-1.5 list-none p-0 m-0">
          <li className="text-xs text-text-primary flex items-center gap-2">
            <span className="text-emerald-400 font-bold">✓</span>
            Standard Title Block recognized
          </li>
          <li className="text-xs text-text-primary flex items-center gap-2">
            <span className="text-amber-400 font-bold">⚠</span>
            4 repeated M3 bolt-hole clusters found
          </li>
          <li className="text-xs text-text-primary flex items-center gap-2">
            <span className="text-blue-400 font-bold">ℹ</span>
            Symmetry identified along Y-axis
          </li>
        </ul>
      </div>

      <div className="bg-white/3 border border-white/5 p-3 rounded-lg flex flex-col gap-2">
        <h3 className="text-xs font-bold text-blue-400 m-0">Similar Geometry Search</h3>
        <p className="text-xs text-text-muted m-0 leading-relaxed">Select a primitive to find identical structures across the CAD canvas.</p>
        <button className="w-full bg-blue-600/15 border border-blue-600/30 text-blue-100 text-xs font-semibold py-2 px-3 rounded-md cursor-pointer hover:bg-blue-600/25 transition-colors">
          Scan for Matching Vectors
        </button>
      </div>
    </div>
  );
};
