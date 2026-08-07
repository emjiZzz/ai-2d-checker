/**
 * Comparison stage definitions, shared between usePhysicalComparison.ts (drives the
 * simulated timing) and TwoDLeftPanel.tsx (renders the labels/progress).
 *
 * The backend returns one final response with no intermediate progress events — these
 * durations are still simulated, not driven by real backend signals. What changed from
 * the old hardcoded 4-step "Scanning Original Drawing / Extracting Metadata / Scanning
 * KMTI Drawing / Comparing Matches" sequence is that the labels are no longer generic:
 * they describe what the backend pipeline actually does
 * (see services/backend/infrastructure/audit/comparison/).
 *
 * These were keyed per comparison_method until ADR-006 removed `rag_ai`, `ai_vision` and
 * `hybrid`. The maps are kept keyed rather than flattened to a single sequence: a room
 * created before the removal can still carry an old method string, and the `?? .rag`
 * fallbacks below turn that into the deterministic sequence instead of an empty list.
 */

export interface ComparisonStage {
  id: string;
  label: string;
  /** Simulated time to sit on this stage before advancing. The last stage in a
   * sequence has no timer — it sits on "Processing..." until the real fetch resolves,
   * same as the original implementation's final "comparing" step. */
  durationMs: number;
}

// Keyed by method name, with `rag` — the pre-rename spelling of the same engine — mapped
// alongside it. A room fetched from a cached response can still carry the old string, and a
// missing key here would show a blank label rather than fall back.
export const COMPARISON_METHOD_LABELS: Record<string, string> = {
  deterministic: "Deterministic",
  rag: "Deterministic",
};

// orchestrator.py::generate_deterministic_candidates — zone/BOM/title extraction, a bounded
// title-block OCR call, then SpatialDiffer + coordinate resolution.
const DETERMINISTIC_STAGES: ComparisonStage[] = [
  { id: "extracting", label: "Extracting drawing entities & BOM/title data", durationMs: 600 },
  { id: "title_block_ocr", label: "Reading title block", durationMs: 700 },
  { id: "spatial_diff", label: "Running deterministic spatial diff", durationMs: 700 },
  { id: "finalizing", label: "Resolving coordinates & finalizing", durationMs: 500 },
];

export const COMPARISON_STAGE_SEQUENCES: Record<string, ComparisonStage[]> = {
  deterministic: DETERMINISTIC_STAGES,
  rag: DETERMINISTIC_STAGES,
};

export function getComparisonStages(method: string | undefined | null): ComparisonStage[] {
  return COMPARISON_STAGE_SEQUENCES[method ?? "deterministic"] ?? DETERMINISTIC_STAGES;
}

export function getComparisonMethodLabel(method: string | undefined | null): string {
  return COMPARISON_METHOD_LABELS[method ?? "deterministic"] ?? "Deterministic";
}

// How long the frontend waits before aborting the request outright. The per-method spread
// (up to 420s for `hybrid`, which ran two generators plus a crop-verification pass) went
// with those methods in ADR-006. The deterministic path makes at most one bounded
// title-block OCR call, so 120s is the only budget left. Still unmeasured — tune once real
// p95 durations are known. The `?? 180_000` below covers a room carrying an old method
// string, deliberately generous rather than clamped to the deterministic budget.
const COMPARISON_TIMEOUT_MS: Record<string, number> = {
  deterministic: 120_000,
  rag: 120_000,
};

export function getComparisonTimeoutMs(method: string | undefined | null): number {
  return COMPARISON_TIMEOUT_MS[method ?? "deterministic"] ?? 180_000;
}
