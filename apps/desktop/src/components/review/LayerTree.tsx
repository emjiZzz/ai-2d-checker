import React from 'react';
import { useReviewStore } from '../../stores/reviewStore';

interface LayerTreeProps {
  availableLayers: string[];
}

export const LayerTree: React.FC<LayerTreeProps> = ({ availableLayers }) => {
  const activeLayers = useReviewStore(s => s.activeLayers);
  const toggleLayer = useReviewStore(s => s.toggleLayer);
  const setAllLayers = useReviewStore(s => s.setAllLayers);

  return (
    <div className="layer-tree bg-bg-card border border-border-color p-4 rounded-lg text-text-primary text-sm" style={{ minWidth: '250px' }}>
      <h3 className="font-bold text-text-secondary mb-4 border-b border-border-color pb-2">Drawing Layers</h3>
      
      <div className="flex gap-2 mb-4">
        <button className="bg-bg-sidebar hover:bg-sidebar-item-hover border border-border-color text-text-primary px-2 py-1 rounded text-xs transition-colors cursor-pointer" onClick={() => setAllLayers(true)}>Show All</button>
        <button className="bg-bg-sidebar hover:bg-sidebar-item-hover border border-border-color text-text-primary px-2 py-1 rounded text-xs transition-colors cursor-pointer" onClick={() => setAllLayers(false)}>Hide All</button>
      </div>

      <div className="layer-list space-y-2 overflow-y-auto max-h-64">
        {availableLayers.map(layer => (
          <label key={layer} className="flex items-center space-x-2 cursor-pointer hover:bg-sidebar-item-hover p-1 rounded">
            <input 
              type="checkbox" 
              className="form-checkbox bg-bg-dark border-border-color rounded text-accent-cyan"
              checked={activeLayers[layer] !== false} // Default true
              onChange={() => toggleLayer(layer)}
            />
            <span className="truncate" title={layer}>{layer}</span>
          </label>
        ))}
      </div>
    </div>
  );
};
