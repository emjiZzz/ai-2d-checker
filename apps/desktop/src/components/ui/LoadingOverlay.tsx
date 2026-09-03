import React from "react";
import { createPortal } from "react-dom";
import { cn } from "../../utils/cn";

export const Z_INDEX = 9998;

export interface LoadingOverlayProps {
  active: boolean;
  title?: string;
  phase?: string | null;
}

const SQUARE_ACCORDION_BLOCKS = ["█", "▓", "▒"] as const;

export interface SquareAccordionProps extends React.ComponentProps<"span"> {
  blocks?: readonly string[];
  size?: number;
  track?: string;
  cellSize?: number;
}

/**
 * Pixel-Perfect SquareAccordion ASCII/Unicode Geometry Loader
 * High-visibility, crisp monospace geometric loader with delayed accordion blocks.
 */
export function SquareAccordion({
  className,
  blocks = SQUARE_ACCORDION_BLOCKS,
  size = 5,
  track = "░",
  cellSize = 24,
  style,
  ...props
}: SquareAccordionProps) {
  const cells = Math.max(2, Math.floor(size));
  const totalPx = cells * cellSize;
  const travelPx = (cells - 1) * cellSize;

  const glyphs = SQUARE_ACCORDION_BLOCKS.map(
    (_, index) => blocks[index] ?? SQUARE_ACCORDION_BLOCKS[index],
  );

  const gridCells = Array.from({ length: cells * cells }, (_, index) => {
    const row = Math.floor(index / cells);
    const col = index % cells;

    return row === 0 || row === cells - 1 || col === 0 || col === cells - 1
      ? track
      : " ";
  });

  return (
    <>
      <style>{`
        @keyframes loading-ui-square-accordion {
          0% {
            transform: translate(0px, 0px);
          }
          15%, 25% {
            transform: translate(var(--loader-x), 0px);
          }
          40%, 50% {
            transform: translate(var(--loader-x), var(--loader-y));
          }
          65%, 75% {
            transform: translate(0px, var(--loader-y));
          }
          90%, 100% {
            transform: translate(0px, 0px);
          }
        }
      `}</style>
      <span
        role="status"
        className={cn(
          "relative inline-flex font-mono leading-none select-none text-accent-cyan",
          className,
        )}
        style={
          {
            width: totalPx,
            height: totalPx,
            fontSize: `${cellSize}px`,
            lineHeight: 1,
            "--loader-x": `${travelPx}px`,
            "--loader-y": `${travelPx}px`,
            ...style,
          } as React.CSSProperties
        }
        {...props}
      >
        {/* Outer Perimeter Track Grid */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 grid text-border-color"
          style={{
            gridTemplateColumns: `repeat(${cells}, ${cellSize}px)`,
            gridTemplateRows: `repeat(${cells}, ${cellSize}px)`,
          }}
        >
          {gridCells.map((glyph, index) => (
            <span
              key={index}
              style={{
                width: cellSize,
                height: cellSize,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {glyph}
            </span>
          ))}
        </span>

        {/* 3 Cascading Accordion Blocks */}
        {glyphs.map((glyph, index) => (
          <span
            key={`${glyph}-${index}`}
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute top-0 left-0 flex items-center justify-center text-accent-cyan font-bold",
              ["z-30", "z-20", "z-10"][index],
            )}
            style={{
              width: cellSize,
              height: cellSize,
              animation:
                "loading-ui-square-accordion var(--duration, 3.2s) linear infinite",
              animationDelay: `calc(var(--delay, 0.1s) * ${index})`,
              backgroundColor: "transparent",
            }}
          >
            {glyph}
          </span>
        ))}
        <span className="sr-only">Loading</span>
      </span>
    </>
  );
}

/**
 * Signature KMTI Loading Overlay (Pure Text & Monospace Geometry)
 */
export const LoadingOverlay: React.FC<LoadingOverlayProps> = ({
  active,
  title = "Exporting PDF Report",
  phase,
}) => {
  if (!active || typeof document === "undefined") return null;

  return createPortal(
    <div
      role="alertdialog"
      aria-busy="true"
      aria-live="polite"
      aria-label={title}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: Z_INDEX,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(15, 23, 42, 0.78)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        cursor: "wait",
        userSelect: "none",
      }}
      onClick={(event) => event.stopPropagation()}
    >
      {/* Centered Minimalist Loading Stack */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: 16,
          maxWidth: "92vw",
        }}
      >
        {/* Prominent SquareAccordion ASCII Geometric Loader */}
        <div style={{ padding: 6, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <SquareAccordion size={5} cellSize={24} />
        </div>

        {/* Operation Title */}
        <div
          style={{
            fontSize: 19,
            fontWeight: 600,
            color: "#f8fafc",
            letterSpacing: "0.01em",
          }}
        >
          {title}
        </div>

        {/* Live Dynamic Phase Subtitle */}
        <div
          style={{
            fontSize: 13,
            color: "#94a3b8",
            maxWidth: 380,
            lineHeight: 1.4,
          }}
        >
          {phase || "Preparing…"}
        </div>
      </div>
    </div>,
    document.body,
  );
};
