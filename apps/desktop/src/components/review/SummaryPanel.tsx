import React, { useEffect, useState } from "react";
import { Sparkles, ShieldAlert, Info } from "lucide-react";
import { getComparisonSummary, type ComparisonSummary } from "../../services/auditsApi";

/**
 * Grounded summary of a session's findings — ADR-010.
 *
 * ## Three rules this component exists to keep
 *
 * **1. It renders BELOW the checklist, never above it.** The structured findings are the product
 * of record; this is derived and disposable. A summary placed above the list invites a reader to
 * stop there.
 *
 * **2. It always states the finding count.** Whatever the status, a reader who stops at the
 * summary still knows how many items they skipped. That is the mitigation for the new failure mode
 * ADR-010 introduces — the summary becoming the thing people read instead of the checklist.
 *
 * **3. A withheld summary shows the deterministic text and SAYS SO.** It is never silently
 * replaced. If verification failed, the reader is told, because "the generated summary was
 * rejected" and "there were no notable changes" must never look the same. `fallback_text` is
 * populated on every status, so there is always something true to render.
 *
 * `status` is a value rather than an absence for the same reason R1's `SearchOutcome` is: "could
 * not answer" and "nothing to report" are different facts and a caller must not be able to
 * conflate them by accident.
 */

interface SummaryPanelProps {
  sessionId: string;
}

const STATUS_NOTE: Record<string, string> = {
  withheld:
    "The generated summary failed verification and was withheld. Showing the deterministic summary instead.",
  unavailable: "No summary provider is available. Showing the deterministic summary.",
  disabled: "Generated summaries are turned off for this workspace.",
  not_applicable: "",
  ok: "",
};

export const SummaryPanel: React.FC<SummaryPanelProps> = ({ sessionId }) => {
  const [summary, setSummary] = useState<ComparisonSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    setLoading(true);
    getComparisonSummary(sessionId)
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Summary request failed.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loading && !summary) {
    return (
      <div className="summary-panel" data-testid="summary-panel">
        <span className="summary-muted">Preparing summary…</span>
      </div>
    );
  }

  if (error) {
    // A transport failure is not the same as "no summary" — say which one happened.
    return (
      <div className="summary-panel" data-testid="summary-panel">
        <span className="summary-muted" role="alert">
          Summary unavailable: {error}
        </span>
      </div>
    );
  }

  if (!summary) return null;

  const note = STATUS_NOTE[summary.status] ?? "";
  const isGenerated = summary.status === "ok";

  return (
    <div className="summary-panel" data-testid="summary-panel">
      <div className="summary-head">
        <Sparkles size={14} />
        <span className="summary-title">Summary</span>
        {/* Rule 2: the count is always visible, on every status. */}
        <span className="summary-count" data-testid="summary-finding-count">
          {summary.finding_count} finding{summary.finding_count === 1 ? "" : "s"}
        </span>
        {isGenerated && summary.model_used && (
          <span className="summary-model">{summary.cached ? "cached · " : ""}{summary.model_used}</span>
        )}
      </div>

      {isGenerated ? (
        <>
          {summary.headline && <p className="summary-headline">{summary.headline}</p>}
          <ul className="summary-claims">
            {summary.claims.map((claim, i) => (
              <li key={i}>
                {claim.text}{" "}
                <span className="summary-cites" title={claim.finding_ids.join(", ")}>
                  ({claim.finding_ids.length} finding{claim.finding_ids.length === 1 ? "" : "s"})
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="summary-fallback" data-testid="summary-fallback">
          {summary.fallback_text}
        </p>
      )}

      {note && (
        <div
          className={`summary-note ${summary.status === "withheld" ? "summary-note-warn" : ""}`}
          data-testid="summary-note"
        >
          {summary.status === "withheld" ? <ShieldAlert size={12} /> : <Info size={12} />}
          <span>{note}</span>
        </div>
      )}

      <style>{`
        .summary-panel {
          margin: 16px 10px 20px;
          padding: 12px;
          min-width: 0;
          box-sizing: border-box;
          overflow-wrap: anywhere;
          border: 1px solid var(--border-color);
          border-radius: 10px;
          background: var(--bg-card, rgba(255,255,255,0.02));
        }
        .summary-head {
          display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
          font-size: 12px; color: var(--text-secondary);
          margin-bottom: 8px;
        }
        .summary-title { font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
        .summary-count {
          font-weight: 600; padding: 1px 8px; border-radius: 999px;
          border: 1px solid var(--border-color);
        }
        .summary-model { opacity: 0.6; font-size: 10px; overflow-wrap: anywhere; }
        .summary-headline {
          font-size: 13px; font-weight: 600; color: var(--text-primary); margin: 0 0 8px;
        }
        .summary-claims { margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.5; color: var(--text-primary); }
        .summary-claims li { margin-bottom: 4px; }
        .summary-cites { color: var(--text-secondary); font-size: 11px; }
        .summary-fallback { font-size: 13px; color: var(--text-primary); margin: 0; }
        .summary-muted { font-size: 12px; color: var(--text-secondary); }
        .summary-note {
          display: flex; align-items: center; gap: 6px;
          margin-top: 10px; font-size: 11px; color: var(--text-secondary);
        }
        .summary-note-warn { color: #fbbf24; }
      `}</style>
    </div>
  );
};

export default SummaryPanel;
