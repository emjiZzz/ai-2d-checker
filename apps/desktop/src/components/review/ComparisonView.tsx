import React from 'react';
import { DrawingCanvas } from './DrawingCanvas';
import { useReviewStore } from '../../stores/reviewStore';

interface ComparisonViewProps {
  baseLayers: Record<string, any[]>;
  newLayers: Record<string, any[]>;
  width: number;
  height: number;
}

export const ComparisonView: React.FC<ComparisonViewProps> = ({ baseLayers, newLayers, width, height }) => {
  const { isComparisonMode } = useReviewStore();

  if (!isComparisonMode) return null;

  return (
    <div className="comparison-view flex w-full" style={{ height }}>
      <div className="flex-1 border-r border-gray-700 relative">
        <div className="absolute top-2 left-2 bg-black/60 text-white px-2 py-1 rounded text-xs z-10 font-mono">
          V1 (Baseline)
        </div>
        <DrawingCanvas layers={baseLayers} width={width / 2} height={height} />
      </div>
      
      <div className="flex-1 relative">
        <div className="absolute top-2 left-2 bg-blue-600/60 text-white px-2 py-1 rounded text-xs z-10 font-mono">
          V2 (Current Upload)
        </div>
        <DrawingCanvas layers={newLayers} width={width / 2} height={height} />
      </div>
    </div>
  );
};
