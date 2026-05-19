import React from 'react';

interface GeometryInspectorProps {
  selectedEntity: any | null;
}

export const GeometryInspector: React.FC<GeometryInspectorProps> = ({ selectedEntity }) => {
  if (!selectedEntity) {
    return (
      <div className="geometry-inspector bg-gray-900 p-4 rounded-lg text-gray-500 text-sm text-center h-32 flex items-center justify-center border border-gray-800">
        Click any DXF primitive to inspect its coordinate vectors and layer parameters.
      </div>
    );
  }

  return (
    <div className="geometry-inspector bg-gray-900 p-4 rounded-lg text-white text-sm border border-gray-700">
      <h3 className="font-bold text-gray-300 border-b border-gray-700 pb-2 mb-3">
        Entity Inspector <span className="text-blue-400 float-right font-mono uppercase">{selectedEntity.type}</span>
      </h3>
      
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs">
        <span className="text-gray-500">ID:</span>
        <span className="truncate" title={selectedEntity.id}>{selectedEntity.id}</span>
        
        <span className="text-gray-500">Layer:</span>
        <span className="text-cyan-400">{selectedEntity.layer || '0'}</span>
        
        {/* Render geometry-specific properties like Start/End or Center/Radius */}
        {Object.entries(selectedEntity.geometry).map(([key, val]) => (
          <React.Fragment key={key}>
            <span className="text-gray-500 capitalize">{key}:</span>
            <span className="text-green-400">{JSON.stringify(val)}</span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};
