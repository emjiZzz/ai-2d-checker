import React, { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { baseUrl, buildHeaders, parseOrThrow } from "../../services/fetchUtils";
import { Loader2 } from "lucide-react";

export const CadFileIcon: React.FC<{ size?: number; className?: string }> = ({ size = 16, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {/* Sheet outline with folded corner */}
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    {/* CAD Precision Bore & Crosshair */}
    <circle cx="11.5" cy="14.5" r="3" strokeWidth="1.5" />
    <line x1="11.5" y1="10" x2="11.5" y2="19" strokeWidth="1" strokeDasharray="1.5 1.5" />
    <line x1="7" y1="14.5" x2="16" y2="14.5" strokeWidth="1" strokeDasharray="1.5 1.5" />
  </svg>
);

interface RealDrawingThumbnailProps {
  drawingId?: string | null;
  hasPair: boolean;
}

interface Entity {
  type: string;
  geometry: any;
  properties?: any;
  style?: {
    stroke?: string;
    strokeWidth?: number;
    color?: string;
    line_weight?: number;
  };
}

export const RealDrawingThumbnail: React.FC<RealDrawingThumbnailProps> = ({
  drawingId,
  hasPair,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Fetch real CAD vector layers from backend
  const { data: layersData, isLoading } = useQuery({
    queryKey: ["drawing_layers_thumb", drawingId],
    queryFn: async () => {
      if (!drawingId) return null;
      const res = await fetch(`${baseUrl()}/api/v1/drawings/${drawingId}/layers`, {
        headers: buildHeaders(),
      });
      const json = await parseOrThrow<any>(res);
      return json?.layers || json || null;
    },
    enabled: !!drawingId,
    staleTime: 10 * 60 * 1000, // 10 min cache
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !layersData) return;

    const render = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (width === 0 || height === 0) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Handle high-DPI
      const dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);

      // Clear transparent to show graph paper background
      ctx.clearRect(0, 0, width, height);

      // Extract all entities across layers
      const allEntities: Entity[] = [];
      Object.values(layersData).forEach((layer: any) => {
        if (Array.isArray(layer)) {
          allEntities.push(...layer);
        }
      });

      if (allEntities.length === 0) return;

      // Calculate real world bounding box
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;

      allEntities.forEach((ent) => {
        const g = ent.geometry;
        if (!g) return;

        if (g.start && g.end) {
          minX = Math.min(minX, g.start[0], g.end[0]);
          minY = Math.min(minY, g.start[1], g.end[1]);
          maxX = Math.max(maxX, g.start[0], g.end[0]);
          maxY = Math.max(maxY, g.start[1], g.end[1]);
        } else if ((g.center || g.location) && (g.radius || ent.properties?.radius)) {
          const c = g.center || g.location;
          const r = g.radius || ent.properties?.radius || 1;
          minX = Math.min(minX, c[0] - r);
          minY = Math.min(minY, c[1] - r);
          maxX = Math.max(maxX, c[0] + r);
          maxY = Math.max(maxY, c[1] + r);
        } else if (Array.isArray(g.points || g.vertices)) {
          const pts = g.points || g.vertices;
          pts.forEach((pt: number[]) => {
            if (Array.isArray(pt) && pt.length >= 2) {
              minX = Math.min(minX, pt[0]);
              minY = Math.min(minY, pt[1]);
              maxX = Math.max(maxX, pt[0]);
              maxY = Math.max(maxY, pt[1]);
            }
          });
        } else if (g.location || g.insert) {
          const loc = g.location || g.insert;
          minX = Math.min(minX, loc[0]);
          minY = Math.min(minY, loc[1]);
          maxX = Math.max(maxX, loc[0]);
          maxY = Math.max(maxY, loc[1]);
        }
      });

      if (!isFinite(minX) || !isFinite(minY) || !isFinite(maxX) || !isFinite(maxY)) {
        return;
      }

      const worldW = maxX - minX || 1;
      const worldH = maxY - minY || 1;

      // Add 8% padding
      const padX = width * 0.08;
      const padY = height * 0.10;
      const availW = width - padX * 2;
      const availH = height - padY * 2;

      const scale = Math.min(availW / worldW, availH / worldH);

      // Transform world coord to thumbnail canvas pixel (CAD Y is flipped)
      const toScreen = (x: number, y: number): [number, number] => {
        const sx = padX + (x - minX) * scale + (availW - worldW * scale) / 2;
        const sy = height - (padY + (y - minY) * scale + (availH - worldH * scale) / 2);
        return [sx, sy];
      };

      // Render real vectors in crisp architectural black
      ctx.lineWidth = 1;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#0f172a";
      ctx.fillStyle = "#0f172a";

      allEntities.forEach((ent) => {
        const g = ent.geometry;
        if (!g) return;

        const type = (ent.type || "").toLowerCase();

        if (type === "line" && g.start && g.end) {
          const [x1, y1] = toScreen(g.start[0], g.start[1]);
          const [x2, y2] = toScreen(g.end[0], g.end[1]);
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        } else if (type === "circle" && (g.center || g.location)) {
          const [cx, cy] = toScreen((g.center || g.location)[0], (g.center || g.location)[1]);
          const r = (g.radius || ent.properties?.radius || 1) * scale;
          if (r > 0.4) {
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.stroke();
          }
        } else if (type === "arc" && (g.center || g.location)) {
          const [cx, cy] = toScreen((g.center || g.location)[0], (g.center || g.location)[1]);
          const r = (g.radius || ent.properties?.radius || 1) * scale;
          const startAngle = -(g.start_angle || 0) * (Math.PI / 180);
          const endAngle = -(g.end_angle || 0) * (Math.PI / 180);
          if (r > 0.4) {
            ctx.beginPath();
            ctx.arc(cx, cy, r, startAngle, endAngle, true);
            ctx.stroke();
          }
        } else if (
          (type === "lwpolyline" || type === "polyline" || type === "spline" || type === "leader" || type === "multileader") &&
          (g.points || g.vertices)
        ) {
          const pts: number[][] = g.points || g.vertices;
          if (pts.length > 1) {
            ctx.beginPath();
            const [firstX, firstY] = toScreen(pts[0][0], pts[0][1]);
            ctx.moveTo(firstX, firstY);
            for (let i = 1; i < pts.length; i++) {
              const [px, py] = toScreen(pts[i][0], pts[i][1]);
              ctx.lineTo(px, py);
            }
            if (g.is_closed || ent.properties?.is_closed || ent.properties?.closed) {
              ctx.closePath();
            }
            ctx.stroke();
          }
        } else if (type === "ellipse" && (g.center || g.location)) {
          const [cx, cy] = toScreen((g.center || g.location)[0], (g.center || g.location)[1]);
          const rx = (g.major_radius || g.radius || 1) * scale;
          const ry = (g.minor_radius || g.radius || 1) * scale;
          if (rx > 0.4 && ry > 0.4) {
            ctx.beginPath();
            ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
      });
    };

    // Render immediately
    render();

    // Re-render on frame & observe resize so returning to page renders instantly
    const rafId = requestAnimationFrame(render);
    const ro = new ResizeObserver(() => {
      render();
    });
    ro.observe(canvas);

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, [layersData]);

  return (
    <div className="relative w-full h-40 bg-bg-dark border border-border-color overflow-hidden flex items-center justify-center select-none group/thumb">
      {/* Real Drawing Canvas */}
      {hasPair && drawingId ? (
        <>
          <canvas
            ref={canvasRef}
            className="w-full h-full object-contain transition-transform duration-300 group-hover/thumb:scale-105"
          />
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-bg-dark/40">
              <Loader2 size={16} className="animate-spin text-accent-cyan" />
            </div>
          )}
        </>
      ) : (
        /* Empty / Draft Blueprint Canvas */
        <div className="flex flex-col items-center justify-center gap-1.5 text-center p-4 z-10">
          <CadFileIcon size={18} className="text-text-muted/60" />
          <span className="text-[9px] text-text-muted/80 font-mono">
            Upload reference &amp; revision files
          </span>
        </div>
      )}
    </div>
  );
};
