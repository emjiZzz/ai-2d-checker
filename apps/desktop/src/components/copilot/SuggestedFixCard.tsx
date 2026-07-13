import React from 'react';

export const SuggestedFixCard: React.FC = () => {
  return (
    <div className="bg-emerald-600/8 border border-emerald-500/25 p-3 rounded-lg flex flex-col gap-2">
      <span className="text-emerald-400 text-[10px] font-bold uppercase tracking-wider">Suggested Fix</span>
      <ol className="pl-3.5 flex flex-col gap-1 text-[11px] text-emerald-200 list-decimal m-0">
        <li>Select the highlighted shaft shoulder geometry.</li>
        <li>Insert a linear dimension indicating total length.</li>
        <li>Apply standard tolerance ±0.05mm per specification.</li>
      </ol>
      <button className="bg-emerald-500/15 border border-emerald-500/30 text-emerald-100 text-xs font-semibold py-2 px-3 rounded-md cursor-pointer hover:bg-emerald-500/25 transition-colors">
        Accept Recommendation (Manual Fix Required)
      </button>
    </div>
  );
};
