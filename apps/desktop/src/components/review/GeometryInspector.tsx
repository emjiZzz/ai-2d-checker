import React from 'react';

interface GeometryInspectorProps {
  selectedEntity: any | null;
}

export const GeometryInspector: React.FC<GeometryInspectorProps> = ({ selectedEntity }) => {
  if (!selectedEntity) {
    return (
      <div className="geometry-inspector bg-bg-card p-4 rounded-lg text-text-muted text-sm text-center h-32 flex items-center justify-center border border-border-color">
        Click any DXF primitive to inspect its coordinate vectors and layer parameters.
      </div>
    );
  }

  return (
    <div className="geometry-inspector bg-bg-card p-4 rounded-lg text-text-primary text-sm border border-border-color">
      <h3 className="font-bold text-text-secondary border-b border-border-color pb-2 mb-3">
        Entity Inspector <span className="text-accent-cyan float-right font-mono uppercase">{selectedEntity.type}</span>
      </h3>
      
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs">
        <span className="text-text-muted">ID:</span>
        <span className="truncate text-text-primary" title={selectedEntity.id}>{selectedEntity.id}</span>
        
        <span className="text-text-muted">Layer:</span>
        <span className="text-accent-cyan font-bold">{selectedEntity.layer || '0'}</span>
        
        {/* Render geometry-specific properties like Start/End or Center/Radius */}
        {Object.entries(selectedEntity.geometry).map(([key, val]) => (
          <React.Fragment key={key}>
            <span className="text-text-muted capitalize">{key}:</span>
            <span className="text-emerald-500 font-semibold">{JSON.stringify(val)}</span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};
