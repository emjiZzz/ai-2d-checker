import React from 'react';

export const StandardsReferenceCard: React.FC = () => {
  return (
    <div className="bg-indigo-600/8 border border-indigo-500/25 p-3 rounded-lg flex flex-col gap-1.5">
      <span className="text-indigo-400 text-[10px] font-bold uppercase tracking-wider">Related Standard</span>
      <h4 className="font-mono text-xs text-indigo-200 m-0">ISO 129-1:2018 (Section 4.2)</h4>
      <p className="text-xs text-indigo-300 border-l-2 border-indigo-500 pl-2 leading-relaxed m-0">
        "All dimensions necessary for the unambiguous definition of a part shall be shown directly on the drawing."
      </p>
    </div>
  );
};
