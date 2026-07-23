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
    <div className="knowledge-graph bg-bg-card text-text-primary p-4 rounded-lg border border-border-color">
      <h3 className="text-md font-bold text-accent-cyan mb-3 flex items-center">
        <span className="mr-2">🕸</span> Engineering Knowledge Graph
      </h3>
      <p className="text-xs text-text-muted mb-4">Semantic relationship lineage mapped dynamically across current active audits:</p>
      
      <div className="space-y-2 max-h-[250px] overflow-y-auto pr-1 custom-scrollbar">
        {mockRelations.map((rel, index) => (
          <div key={index} className="flex items-center text-xs bg-bg-sidebar border border-border-color p-2 rounded">
            <span className="font-semibold text-text-secondary">{rel.source}</span>
            <span className="mx-2 px-1.5 py-0.5 bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan text-[9px] rounded font-mono uppercase tracking-wider">
              {rel.type}
            </span>
            <span className="font-semibold text-accent-cyan">{rel.target}</span>
          </div>
        ))}
      </div>
      
      <button className="mt-4 w-full bg-bg-sidebar hover:bg-sidebar-item-hover border border-border-color text-text-primary text-xs font-semibold py-2 rounded transition-colors cursor-pointer">
        Visualize Dependency Traversal
      </button>
    </div>
  );
};
