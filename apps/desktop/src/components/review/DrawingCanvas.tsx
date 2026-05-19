import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Stage, Container, Graphics } from '@pixi/react';
import { useReviewStore } from '../../stores/reviewStore';

interface EntityPayload {
  id: string;
  type: string;
  geometry: any;
  style: any;
}

interface DrawingCanvasProps {
  layers: Record<string, EntityPayload[]>;
  width: number;
  height: number;
}

const LayerGraphics: React.FC<{ entities: EntityPayload[] }> = React.memo(({ entities }) => {
  const draw = useCallback((g: any) => {
    g.clear();
    entities.forEach(ent => {
      // Very basic stroke mapping
      g.lineStyle(ent.style.strokeWidth || 1, parseInt(ent.style.stroke.replace('#', '0x')) || 0xFFFFFF, 1);
      
      const geo = ent.geometry;
      if (ent.type === 'line' && geo.start && geo.end) {
        g.moveTo(geo.start[0], geo.start[1]);
        g.lineTo(geo.end[0], geo.end[1]);
      } else if (ent.type === 'circle' && geo.center) {
        g.drawCircle(geo.center[0], geo.center[1], geo.radius || 1);
      }
    });
  }, [entities]);

  return <Graphics draw={draw} />;
});

export const DrawingCanvas: React.FC<DrawingCanvasProps> = ({ layers, width, height }) => {
  const { viewport, setViewport, activeLayers } = useReviewStore();
  
  const handleWheel = (e: any) => {
    e.evt.preventDefault();
    const scaleBy = 1.1;
    const oldScale = viewport.scale;
    const newScale = e.evt.deltaY > 0 ? oldScale / scaleBy : oldScale * scaleBy;
    
    // Zoom relative to pointer
    const stage = e.currentTarget;
    const pointerPosition = stage.getPointerPosition();
    
    // This requires proper Pixi Interaction Manager math in production
    setViewport({ ...viewport, scale: Math.max(0.01, Math.min(newScale, 100)) });
  };

  return (
    <div style={{ width, height, overflow: 'hidden', backgroundColor: '#1E1E1E' }}>
      <Stage 
        width={width} 
        height={height} 
        options={{ backgroundAlpha: 0, antialias: true }}
        onWheel={handleWheel}
      >
        <Container 
          x={viewport.x} 
          y={viewport.y} 
          scale={{ x: viewport.scale, y: viewport.scale }}
        >
          {Object.entries(layers).map(([layerName, entities]) => {
            if (activeLayers[layerName] === false) return null;
            return <LayerGraphics key={layerName} entities={entities} />;
          })}
        </Container>
      </Stage>
    </div>
  );
};
