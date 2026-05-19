// Web Worker for off-thread geometry processing
self.onmessage = (e: MessageEvent) => {
  const { type, payload } = e.data;

  if (type === 'PROCESS_GEOMETRY_CHUNK') {
    const { entities } = payload;
    
    // Convert backend payload into typed arrays for PixiJS WebGL buffers
    const processedLayers: Record<string, any[]> = {};
    let entityCount = 0;

    entities.forEach((ent: any) => {
      if (!processedLayers[ent.layer]) {
        processedLayers[ent.layer] = [];
      }
      
      // Compute bounding box for spatial indexing (QuadTree preparation)
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      
      if (ent.type === 'line' && ent.geometry.start && ent.geometry.end) {
        minX = Math.min(ent.geometry.start[0], ent.geometry.end[0]);
        maxX = Math.max(ent.geometry.start[0], ent.geometry.end[0]);
        minY = Math.min(ent.geometry.start[1], ent.geometry.end[1]);
        maxY = Math.max(ent.geometry.start[1], ent.geometry.end[1]);
      } else if (ent.type === 'circle' && ent.geometry.center) {
        const r = ent.geometry.radius || 1;
        minX = ent.geometry.center[0] - r;
        maxX = ent.geometry.center[0] + r;
        minY = ent.geometry.center[1] - r;
        maxY = ent.geometry.center[1] + r;
      }
      
      processedLayers[ent.layer].push({
        ...ent,
        _bounds: { minX, minY, maxX, maxY }
      });
      entityCount++;
    });

    self.postMessage({
      type: 'CHUNK_PROCESSED',
      payload: { processedLayers, entityCount }
    });
  }
};
