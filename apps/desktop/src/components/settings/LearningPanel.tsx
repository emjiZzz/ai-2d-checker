import React, { useCallback, useEffect, useState } from "react";
import { Brain, RefreshCw } from "lucide-react";
import { getLearnedModelStatus, retrainLearnedModel, type LearnedModelStatus } from "../../services/auditsApi";

/**
 * Read-back surface for the human-in-the-loop learned-correction model. Shows how many
 * corrections have been captured, whether the generalizing model is active or still "warming
 * up" toward its minimum training threshold, the exact-override count, and CV metrics — plus a
 * manual Retrain button. This is the honest cold-start surface: with few corrections the model
 * abstains and this panel says so.
 */
/**
 * Below this much accuracy over the majority-class baseline, the head is barely doing more than
 * predicting the common answer. Mirrors `MIN_MEANINGFUL_LIFT` in `tools/label_status.py`, which
 * in turn mirrors the 0.15 lift gate `retrieval/metrics.py` applies to recall over its chance
 * floor. Hand-mirrored across the language boundary, like the comparison taxonomy — pinned by
 * `LearningPanel.test.tsx`.
 */
export const MIN_MEANINGFUL_LIFT = 0.15;

const numberOrNull = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export const LearningPanel: React.FC = () => {
  const [status, setStatus] = useState<LearnedModelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      setStatus(await getLearnedModelStatus());
    } catch (err: any) {
      setError(err?.message || String(err));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const retrain = async () => {
    setBusy(true);
    try {
      setStatus(await retrainLearnedModel());
      setError(null);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const minTrain = status?.min_train ?? 40;
  const nVerdict = status?.n_verdict ?? 0;
  const pct = minTrain > 0 ? Math.min(100, Math.round((nVerdict / minTrain) * 100)) : 0;
  const ready = !!status?.verdict_ready;

  // Both come from the bundle the backend trained, never recomputed here: the panel and
  // `tools/label_status.py` must not be able to disagree about what the model scored.
  // `verdict_majority_baseline` was added 2026-08-17, so a bundle trained before that has the
  // accuracy and no floor — rendered as the bare accuracy rather than a wrong comparison.
  const cvAccuracy = numberOrNull(status?.metrics?.verdict_cv_accuracy);
  const majorityBaseline = numberOrNull(status?.metrics?.verdict_majority_baseline);
  const lift =
    cvAccuracy !== null && majorityBaseline !== null ? cvAccuracy - majorityBaseline : null;

  return (
    <div className="bg-bg-card border border-border-color rounded-xl p-6 backdrop-blur-md shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold border-l-[3px] border-accent-cyan pl-2.5 text-text-primary m-0 flex items-center gap-2">
          <Brain size={15} /> Learned Correction Model
        </h3>
        <button
          onClick={retrain}
          disabled={busy}
          className="flex items-center gap-1.5 text-[11px] font-semibold text-accent-cyan border border-border-color rounded-lg px-3 py-1.5 hover:bg-sidebar-item-hover transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} className={busy ? "spin-animation" : ""} /> Retrain now
        </button>
      </div>

      <p className="text-[11px] text-text-muted mt-2 leading-relaxed">
        Trained purely on your corrections — no LLM. It flips false CHANGED→MATCHED, confirms real
        changes, and reclassifies findings once it has enough examples.
      </p>

      {error && (
        <div className="mt-4 text-[11px] text-red-400 bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {status && (
        <div className="mt-5 flex flex-col gap-4">
          <div>
            <div className="flex items-center justify-between text-[11px] mb-1.5">
              <span className="text-text-muted">
                {ready ? "Model active" : "Model warming up"}
              </span>
              <span className={ready ? "text-emerald-400 font-semibold" : "text-accent-cyan font-semibold"}>
                {ready ? "✓ generalizing" : `${nVerdict}/${minTrain} corrections`}
              </span>
            </div>
            <div className="w-full h-1 bg-border-color rounded overflow-hidden">
              <div
                className={`h-full ${ready ? "bg-emerald-400" : "bg-accent-cyan"} transition-all`}
                style={{ width: `${ready ? 100 : pct}%` }}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <Stat label="Total corrections" value={status.n_total} />
            <Stat label="Verdict labels" value={status.n_verdict} />
            <Stat label="Reclassifications" value={status.n_category} />
            <Stat label="Exact overrides" value={status.n_exact_overrides} />
          </div>

          <div className="text-[10px] text-text-muted font-mono">
            Last trained: {status.trained_at ? new Date(status.trained_at).toLocaleString() : "never"}
            {typeof cvAccuracy === "number" && (
              <> · CV accuracy: {(cvAccuracy * 100).toFixed(1)}%</>
            )}
            {typeof cvAccuracy === "number" && typeof majorityBaseline === "number" && (
              <>
                {" "}
                vs {(majorityBaseline * 100).toFixed(1)}% baseline (
                {lift !== null && lift >= 0 ? "+" : ""}
                {lift !== null ? (lift * 100).toFixed(1) : "?"}%)
              </>
            )}
          </div>

          {/*
            The accuracy is never shown alone. On the live corpus (71 class-0 against 41 class-1)
            always answering "not a real change" scores 63.4%, so a bare "73.3% accuracy" reads as
            strong when it is ten points of skill. Same rule the retrieval side already enforces,
            where every rate is printed beside its chance floor.
          */}
          {typeof lift === "number" && lift < MIN_MEANINGFUL_LIFT && (
            <div className="text-[10px] text-amber-400/90 leading-relaxed">
              The model is only {(lift * 100).toFixed(1)}% better than always predicting the
              majority answer. In drawing views, notes and isometric views that answer is
              &ldquo;no change&rdquo;, so a weak head suppresses findings rather than filtering
              noise.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="bg-bg-sidebar border border-border-color rounded-lg px-3 py-2 flex flex-col gap-0.5">
    <span className="text-[9px] font-semibold uppercase tracking-wider text-text-muted">{label}</span>
    <span className="text-base font-bold text-text-primary font-mono">{value}</span>
  </div>
);
