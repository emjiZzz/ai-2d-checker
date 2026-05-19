import React from 'react';

export const KnowledgeGraphPanel: React.FC = () => {
  // Mock node connections representing our backend GraphBuilder lineage
  const mockRelations = [
    { source: "Shaft Geometry #e102", type: "CITES", target: "ISO 286 (Tolerances)" },
    { source: "Shaft Geometry #e102", type: "HAS_VIOLATION", target: "Missing Tolerance #v9" },
    { source: "Missing Tolerance #v9", type: "SECTOR_RISK", target: "High Shaft Friction" },
    { source: "ISO 286 (Tolerances)", type: "PREREQUISITE", target: "General Drafting Rules" }
  ];

  return (
    <div className="knowledge-graph bg-gray-900 text-gray-100 p-4 rounded-lg border border-gray-800">
      <h3 className="text-md font-bold text-blue-400 mb-3 flex items-center">
        <span className="mr-2">🕸</span> Engineering Knowledge Graph
      </h3>
      <p className="text-xs text-gray-400 mb-4">Semantic relationship lineage mapped dynamically across current active audits:</p>
      
      <div className="space-y-2 max-h-[250px] overflow-y-auto pr-1 custom-scrollbar">
        {mockRelations.map((rel, index) => (
          <div key={index} className="flex items-center text-xs bg-gray-800 border border-gray-700/50 p-2 rounded">
            <span className="font-semibold text-gray-300">{rel.source}</span>
            <span className="mx-2 px-1.5 py-0.5 bg-indigo-900/40 border border-indigo-800 text-indigo-300 text-[9px] rounded font-mono uppercase tracking-wider">
              {rel.type}
            </span>
            <span className="font-semibold text-blue-300">{rel.target}</span>
          </div>
        ))}
      </div>
      
      <button className="mt-4 w-full bg-indigo-700/40 hover:bg-indigo-600/40 border border-indigo-600 text-indigo-200 text-xs font-semibold py-2 rounded transition-colors">
        Visualize Dependency Traversal
      </button>
    </div>
  );
};
