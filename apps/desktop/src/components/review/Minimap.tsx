import React from 'react';
import { useReviewStore } from '../../stores/reviewStore';

interface MinimapProps {
  totalWidth: number;
  totalHeight: number;
  containerWidth: number;
  containerHeight: number;
}

export const Minimap: React.FC<MinimapProps> = ({ totalWidth, totalHeight, containerWidth, containerHeight }) => {
  const { viewport, setViewport } = useReviewStore();
  
  const minimapSize = 150;
  const ratio = Math.min(minimapSize / totalWidth, minimapSize / totalHeight);
  
  const scaledWidth = totalWidth * ratio;
  const scaledHeight = totalHeight * ratio;

  // Viewport box in minimap space
  const vpWidth = (containerWidth / viewport.scale) * ratio;
  const vpHeight = (containerHeight / viewport.scale) * ratio;
  const vpX = (-viewport.x / viewport.scale) * ratio;
  const vpY = (-viewport.y / viewport.scale) * ratio;

  const handleMinimapClick = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Map back to canvas space
    const targetX = -(x / ratio) * viewport.scale + (containerWidth / 2);
    const targetY = -(y / ratio) * viewport.scale + (containerHeight / 2);
    
    setViewport({ ...viewport, x: targetX, y: targetY });
  };

  return (
    <div 
      className="minimap absolute bottom-4 left-4 bg-gray-900/80 border border-gray-600 shadow-xl overflow-hidden cursor-crosshair z-20 rounded"
      style={{ width: scaledWidth, height: scaledHeight }}
      onClick={handleMinimapClick}
    >
      {/* Viewport indicator box */}
      <div 
        className="absolute border-2 border-red-500 bg-red-500/20"
        style={{
          width: vpWidth,
          height: vpHeight,
          left: vpX,
          top: vpY,
          transition: 'all 0.1s ease-out'
        }}
      />
    </div>
  );
};
