import { AlertTriangle } from "lucide-react";
import type { DrawingItem } from "../../stores/workspace/types";

/**
 * Warns that the sheet on screen was extracted under an older schema, so it is drawing wrong.
 *
 * ## Why this is worth a badge at all
 *
 * `render_paths`, dimension text anchors, leader hooklines, leader arrowheads, MTEXT rotation
 * and the angular-dimension degree conversion are all computed at **extraction** time. A
 * drawing ingested before one of those fixes keeps rendering without it until
 * `POST /drawings/{id}/reextract` — and it looks like a perfectly ordinary drawing the whole
 * time. An engineer marking up a v2 sheet is reading missing arrowheads, short leader landings
 * and a dimension that says `1.05` where the paper says `60°`.
 *
 * Measured 2026-08-20 with `tools/extraction_status.py`: **36 of 55 stored drawings were
 * stale**, 20 of them five versions behind.
 *
 * ## Renders nothing when the drawing is current
 *
 * Deliberate, and the reason this is safe to put in a always-visible panel. A warning that is
 * always on is one people stop seeing within a day, so the healthy state must be *invisible*
 * rather than a reassuring green tick. `StaleExtractionBadge.test.tsx` pins that.
 *
 * ⚠ **The staleness rule is not evaluated here.** `extraction_is_stale` is computed by the
 * server beside `EXTRACTION_SCHEMA_VERSION`. Comparing the two numbers in TypeScript would put
 * a second copy of the rule on the far side of a language boundary with no shared types — the
 * same drift the taxonomy needs `tests/test_taxonomy_consistency.py` to police. This component
 * only renders what it is told.
 */
export function StaleExtractionBadge({
  drawing,
  label,
}: {
  drawing: DrawingItem | null | undefined;
  label?: string;
}) {
  // `undefined` means the backend predates the field, which is not the same claim as "current"
  // — but it is also not evidence of staleness, and inventing a warning from missing data is
  // how a badge loses its credibility. Absent flag, no badge.
  if (!drawing?.extraction_is_stale) return null;

  const stored = drawing.extraction_schema_version;
  const current = drawing.current_extraction_schema_version;
  const versions =
    typeof stored === "number" && typeof current === "number"
      ? `v${stored || "?"} of v${current}`
      : null;

  return (
    <div
      className="flex items-start gap-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2.5 mb-3 shrink-0"
      role="status"
    >
      <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-px" aria-hidden="true" />
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-[11px] font-bold text-amber-500 uppercase tracking-wider">
          {label ? `${label}: outdated extraction` : "Outdated extraction"}
          {versions ? <span className="font-mono normal-case ml-1.5">({versions})</span> : null}
        </span>
        <span className="text-[11px] text-text-muted leading-relaxed">
          This sheet was parsed by an older version, so parts of it may draw incorrectly —
          arrowheads, leader lines and dimension text most of all. Re-extract it to see the
          drawing as the CAD file actually defines it.
        </span>
      </div>
    </div>
  );
}
