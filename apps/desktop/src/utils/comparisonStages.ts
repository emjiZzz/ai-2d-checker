/**
 * Per-method comparison stage definitions, shared between usePhysicalComparison.ts
 * (drives the simulated timing) and TwoDLeftPanel.tsx (renders the labels/progress).
 *
 * The backend returns one final response with no intermediate progress events — these
 * durations are still simulated, not driven by real backend signals. What changed from
 * the old hardcoded 4-step "Scanning Original Drawing / Extracting Metadata / Scanning
 * KMTI Drawing / Comparing Matches" sequence is that the labels are no longer generic:
 * each comparison_method gets the stage list that actually describes what that method's
 * backend pipeline does (see services/backend/infrastructure/audit/comparison/).
 */

export interface ComparisonStage {
  id: string;
  label: string;
  /** Simulated time to sit on this stage before advancing. The last stage in a
   * sequence has no timer — it sits on "Processing..." until the real fetch resolves,
   * same as the original implementation's final "comparing" step. */
  durationMs: number;
}

export const COMPARISON_METHOD_LABELS: Record<string, string> = {
  rag: "RAG",
  rag_ai: "RAG + AI",
  ai_vision: "AI Vision",
  hybrid: "Hybrid",
};

export const COMPARISON_STAGE_SEQUENCES: Record<string, ComparisonStage[]> = {
  // orchestrator.py::generate_deterministic_candidates — zone/BOM/title extraction,
  // a bounded title-block OCR call, then SpatialDiffer + coordinate resolution.
  rag: [
    { id: "extracting", label: "Extracting drawing entities & BOM/title data", durationMs: 600 },
    { id: "title_block_ocr", label: "Reading title block", durationMs: 700 },
    { id: "spatial_diff", label: "Running deterministic spatial diff", durationMs: 700 },
    { id: "finalizing", label: "Resolving coordinates & finalizing", durationMs: 500 },
  ],
  // full_ai_orchestrator.py::perform_full_ai_comparison(method="rag_ai") — structured
  // CAD context assembled and handed to Gemini alongside the rendered PNGs.
  rag_ai: [
    { id: "extracting", label: "Extracting drawing entities & BOM/title data", durationMs: 700 },
    { id: "building_context", label: "Building structured context for Gemini", durationMs: 600 },
    { id: "gemini_analyzing", label: "Gemini analyzing (RAG + AI)", durationMs: 1800 },
    { id: "finalizing", label: "Resolving coordinates & finalizing", durationMs: 500 },
  ],
  // full_ai_orchestrator.py::perform_full_ai_comparison(method="ai_vision") — only the
  // two rendered PNGs go to Gemini, no structured context.
  ai_vision: [
    { id: "rendering", label: "Rendering drawings for AI Vision", durationMs: 600 },
    { id: "gemini_analyzing", label: "Gemini analyzing (images only)", durationMs: 2000 },
    { id: "finalizing", label: "Resolving coordinates & finalizing", durationMs: 500 },
  ],
  // hybrid_orchestrator.py::perform_hybrid_comparison — two independent generators run
  // concurrently, their candidates are reconciled by location, and any disagreement
  // goes through a narrow crop-based verifier before the final result is assembled.
  hybrid: [
    { id: "dual_generators", label: "Running deterministic diff + AI Vision scan in parallel", durationMs: 1800 },
    { id: "reconciling", label: "Reconciling findings between generators", durationMs: 600 },
    { id: "verifying", label: "Verifying disputed findings", durationMs: 1200 },
    { id: "finalizing", label: "Finalizing results", durationMs: 500 },
  ],
};

export function getComparisonStages(method: string | undefined | null): ComparisonStage[] {
  return COMPARISON_STAGE_SEQUENCES[method ?? "rag"] ?? COMPARISON_STAGE_SEQUENCES.rag;
}

export function getComparisonMethodLabel(method: string | undefined | null): string {
  return COMPARISON_METHOD_LABELS[method ?? "rag"] ?? "RAG";
}

// How long the frontend waits before aborting the request outright. A flat 180s for
// every method caused real failures ("signal is aborted without reason") on hybrid:
// its pipeline runs two generators, then reconciliation, then a crop-verification
// call per batch of disputed findings — structurally more work than the other three
// methods' single Gemini call, so it needs more headroom even after the backend fix
// (crop_verifier.py's batches now run concurrently instead of sequentially, which
// helps a lot but doesn't make hybrid as fast as a single-call method on a drawing
// pair with many disputed findings). Unmeasured, generous placeholders — tune once
// real p95 durations per method are known.
const COMPARISON_TIMEOUT_MS: Record<string, number> = {
  rag: 120_000,
  rag_ai: 240_000,
  ai_vision: 240_000,
  hybrid: 420_000,
};

export function getComparisonTimeoutMs(method: string | undefined | null): number {
  return COMPARISON_TIMEOUT_MS[method ?? "rag"] ?? 180_000;
}
