import type { RefObject } from 'react';

/**
 * Where the two drawing canvases publish their export handle.
 *
 * ## Why a registry rather than a prop
 *
 * `TwoDWorkspace` owns both `DrawingCanvas` refs, but the PDF button exists in TWO places: the
 * workspace top bar, which has them, and `ManualMarkingList`, which is four components away and
 * had none. The manual-check room's "Export PDF Report" therefore produced a report with no
 * drawing in it at all — the one thing the report is for — and nothing anywhere reported a
 * failure, because `canvasRefs?.old?.current?.exportImage?.()` is optional the whole way down.
 *
 * Prop-drilling the refs through `TwoDLeftPanel` would fix that one call site and leave the next
 * one to rediscover it. One registry means every caller reaches the same handle by the same name,
 * and `useComplianceReportExport` no longer takes canvas refs at all.
 *
 * The REF OBJECT is registered, not the handle it currently holds: a canvas panel unmounts and
 * remounts whenever flexlayout moves its tab, and a captured handle would go stale silently while
 * the ref object stays valid across the whole workspace's life.
 */

export interface DrawingExportHandle {
  exportImage?: (exportWidth?: number, exportHeight?: number) => string;
}

export type ExportCanvasSide = 'ref' | 'rev';

const registry: Record<ExportCanvasSide, RefObject<DrawingExportHandle | null> | null> = {
  ref: null,
  rev: null,
};

export function registerExportCanvas(
  side: ExportCanvasSide,
  ref: RefObject<DrawingExportHandle | null> | null,
): void {
  registry[side] = ref;
}

/**
 * A PNG data URL of one sheet, or `null` when that canvas is not mounted.
 *
 * `null` is distinguishable from a blank export on purpose. `toDataURL` on a canvas that failed
 * to allocate still returns a valid — and entirely empty — PNG, so the caller cannot tell "no
 * canvas" from "canvas drew nothing"; the length check below catches the degenerate case that
 * jsPDF would otherwise embed as a white rectangle.
 */
export function exportCanvasImage(
  side: ExportCanvasSide,
  width?: number,
  height?: number,
): string | null {
  const data = registry[side]?.current?.exportImage?.(width, height);
  if (!data || data.length < 512) return null;
  return data;
}
