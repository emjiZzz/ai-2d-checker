import React from 'react';
import type { ViewPreset } from './ThreeDViewer';

interface ViewCubeIconProps {
  face: ViewPreset;
  size?: number;
  active?: boolean;
}

/**
 * Standard CAD Orientation Icons (matching SolidWorks / iCAD / Inventor).
 * - For SE, SW, NE, NW: Renders the classic 3D isometric step block glyph.
 * - For Top, Front, Right, Left, Back, Bottom: Renders an oblique wireframe cube with highlighted face.
 */
export const ViewCubeIcon: React.FC<ViewCubeIconProps> = ({ face, size = 16, active = false }) => {
  const gradId = `viewcube-grad-${face}-${active ? 'act' : 'inact'}`;

  // Colors for isometric step block
  const t_col = active ? '#93c5fd' : '#7cb3f2';
  const l_col = active ? '#60a5fa' : '#3b82f6';
  const r_col = active ? '#2563eb' : '#1d4ed8';
  const s_col = '#1e3a8a';

  if (face === 'sw') {
    // SW Isometric (Icon 1): low front-left step, tall back-right tower
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className="shrink-0 pointer-events-none">
        <polygon points="9.5,1.5 13.2,3.4 9.8,5.2 6.1,3.4" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="13.2,9.2 9.8,11.0 9.8,5.2 13.2,3.4" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="6.1,9.2 9.8,11.0 9.8,5.2 6.1,3.4" fill={l_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="6.1,5.5 9.8,7.3 6.1,9.1 2.4,7.3" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="9.8,11.0 6.1,12.8 6.1,9.1 9.8,7.3" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="2.4,11.0 6.1,12.8 6.1,9.1 2.4,7.3" fill={l_col} stroke={s_col} strokeWidth="0.6" />
      </svg>
    );
  }

  if (face === 'se') {
    // SE Isometric (Icon 4): low front-right step, tall back-left tower
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className="shrink-0 pointer-events-none">
        <polygon points="6.5,1.5 10.2,3.4 6.8,5.2 3.1,3.4" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="10.2,9.2 6.8,11.0 6.8,5.2 10.2,3.4" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="3.1,9.2 6.8,11.0 6.8,5.2 3.1,3.4" fill={l_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="9.9,5.5 13.6,7.3 9.9,9.1 6.2,7.3" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="13.6,11.0 9.9,12.8 9.9,9.1 13.6,7.3" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="6.2,11.0 9.9,12.8 9.9,9.1 6.2,7.3" fill={l_col} stroke={s_col} strokeWidth="0.6" />
      </svg>
    );
  }

  if (face === 'ne') {
    // NE Isometric: low back-right step, tall front-left tower
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className="shrink-0 pointer-events-none">
        <polygon points="9.9,3.7 13.6,5.5 9.9,7.3 6.2,5.5" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="13.6,9.2 9.9,11.0 9.9,7.3 13.6,5.5" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="6.2,9.2 9.9,11.0 9.9,7.3 6.2,5.5" fill={l_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="6.1,1.5 9.8,3.3 6.1,5.1 2.4,3.3" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="9.8,11.0 6.1,12.8 6.1,5.1 9.8,3.3" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="2.4,11.0 6.1,12.8 6.1,5.1 2.4,3.3" fill={l_col} stroke={s_col} strokeWidth="0.6" />
      </svg>
    );
  }

  if (face === 'nw') {
    // NW Isometric: low back-left step, tall front-right tower
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className="shrink-0 pointer-events-none">
        <polygon points="6.1,3.7 9.8,5.5 6.1,7.3 2.4,5.5" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="9.8,9.2 6.1,11.0 6.1,7.3 9.8,5.5" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="2.4,9.2 6.1,11.0 6.1,7.3 2.4,5.5" fill={l_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="9.9,1.5 13.6,3.3 9.9,5.1 6.2,3.3" fill={t_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="13.6,11.0 9.9,12.8 9.9,5.1 13.6,3.3" fill={r_col} stroke={s_col} strokeWidth="0.6" />
        <polygon points="6.2,11.0 9.9,12.8 9.9,5.1 6.2,3.3" fill={l_col} stroke={s_col} strokeWidth="0.6" />
      </svg>
    );
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="shrink-0 pointer-events-none"
    >
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={active ? '#60a5fa' : '#3b82f6'} />
          <stop offset="100%" stopColor={active ? '#2563eb' : '#1d4ed8'} />
        </linearGradient>
      </defs>

      {/* Shaded face */}
      {face === 'top' && (
        <polygon
          points="2.5,5.5 5,2 13.5,2 11,5.5"
          fill={`url(#${gradId})`}
          stroke="#2563eb"
          strokeWidth={0.8}
        />
      )}

      {face === 'bottom' && (
        <polygon
          points="2.5,14 5,10.5 13.5,10.5 11,14"
          fill={`url(#${gradId})`}
          stroke="#2563eb"
          strokeWidth={0.8}
        />
      )}

      {face === 'left' && (
        <polygon
          points="2.5,5.5 5,2 5,10.5 2.5,14"
          fill={`url(#${gradId})`}
          stroke="#2563eb"
          strokeWidth={0.8}
        />
      )}

      {face === 'back' && (
        <polygon
          points="5,2 13.5,2 13.5,10.5 5,10.5"
          fill={`url(#${gradId})`}
          stroke="#2563eb"
          strokeWidth={0.8}
        />
      )}

      {face === 'right' && (
        <polygon
          points="11,5.5 13.5,2 13.5,10.5 11,14"
          fill={`url(#${gradId})`}
          stroke="#2563eb"
          strokeWidth={0.8}
        />
      )}

      {face === 'front' && (
        <polygon
          points="2.5,5.5 11,5.5 11,14 2.5,14"
          fill={`url(#${gradId})`}
          stroke="#2563eb"
          strokeWidth={0.8}
        />
      )}

      {/* Wireframe edges (Steel blue CAD lines) */}
      <rect
        x="5"
        y="2"
        width="8.5"
        height="8.5"
        fill="none"
        stroke="#475569"
        strokeWidth={0.75}
        opacity={active ? 0.6 : 0.4}
      />
      <line x1="2.5" y1="5.5" x2="5" y2="2" stroke="#475569" strokeWidth={0.75} opacity={active ? 0.8 : 0.55} />
      <line x1="11" y1="5.5" x2="13.5" y2="2" stroke="#475569" strokeWidth={0.75} opacity={active ? 0.8 : 0.55} />
      <line x1="11" y1="14" x2="13.5" y2="10.5" stroke="#475569" strokeWidth={0.75} opacity={active ? 0.8 : 0.55} />
      <line x1="2.5" y1="14" x2="5" y2="10.5" stroke="#475569" strokeWidth={0.75} opacity={active ? 0.5 : 0.35} />
      <rect
        x="2.5"
        y="5.5"
        width="8.5"
        height="8.5"
        fill="none"
        stroke="#475569"
        strokeWidth={0.85}
        opacity={active ? 0.9 : 0.75}
      />
    </svg>
  );
};
