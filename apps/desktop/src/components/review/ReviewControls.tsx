import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Loader2, RotateCcw } from "lucide-react";
import {
  reviewViolation,
  type ViolationResolution,
} from "../../services/auditsApi";

/**
 * Supervisor verdict controls for a violation card.
 *
 * ## Why this exists
 *
 * `PATCH /audits/violations/{id}/review` shipped with **no caller anywhere in this app**. Nothing
 * rendered a button for it, so all 1,322 violations in the database were unreviewed and the
 * `lessons` retrieval collection was permanently empty — a read path querying an index no writer
 * could populate. That was never user neglect; there was no UI. This is that UI.
 *
 * ## Approve and Reject are different signals, and only one of them teaches
 *
 * **Approve** says the engine was right. It feeds the `lessons` index (the backend re-derives it
 * from confirmed violations on each review), so a confirmed finding informs later audits.
 *
 * **Reject** says the engine raised something a human judged wrong. It is recorded and it is
 * *deliberately not* indexed as a lesson — feeding a false positive back as a lesson teaches the
 * opposite of the intended thing. Its value is measurement, not learning: rejections are the only
 * record this system has of its own false-positive rate.
 *
 * ## Three states, not two
 *
 * `is_resolved` is a boolean and cannot express "nobody has looked at this yet" — an unreviewed
 * finding and a REJECTED one both read `false`. This component keys off `resolution_type`
 * (`null | APPROVED | REJECTED`) for exactly that reason. Rendering a rejected finding as
 * unreviewed would put it back in the queue forever, which is the failure mode that makes a
 * review queue useless after one pass.
 *
 * ## A verdict can be changed
 *
 * The endpoint is a PATCH and is idempotent, so re-reviewing overwrites. There is no "unreview"
 * — the backend has no null-ing path — so the control offers "Change verdict", which reopens the
 * buttons rather than pretending an unreviewed state can be restored. Claiming otherwise in the
 * UI would be a lie about what the server can do.
 */

interface ReviewControlsProps {
  violationId: string;
  /** Current server-side verdict. `null`/`undefined` means unreviewed. */
  resolution: ViolationResolution | undefined;
  /** Remarks already recorded against this finding, if any. */
  remarks?: string | null;
  /** Fired after the server confirms, with the values the server actually stored. */
  onReviewed?: (result: { resolution: ViolationResolution; remarks: string }) => void;
}

export const ReviewControls: React.FC<ReviewControlsProps> = ({
  violationId,
  resolution,
  remarks,
  onReviewed,
}) => {
  const [pending, setPending] = useState<null | "approve" | "reject">(null);
  const [error, setError] = useState<string | null>(null);
  const [draftRemarks, setDraftRemarks] = useState(remarks ?? "");
  const [reopened, setReopened] = useState(false);

  const decided = resolution === "APPROVED" || resolution === "REJECTED";
  const showButtons = !decided || reopened;

  const submit = async (isValid: boolean) => {
    setPending(isValid ? "approve" : "reject");
    setError(null);
    try {
      const result = await reviewViolation(violationId, isValid, draftRemarks.trim());
      setReopened(false);
      onReviewed?.({
        resolution: result.resolution_type,
        remarks: result.checker_remarks ?? "",
      });
    } catch (err) {
      // Surface it. A review that silently failed to save is worse than one that never happened:
      // the supervisor believes the finding is handled and it is still in the queue.
      setError(err instanceof Error ? err.message : "Review failed to save.");
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="review-controls" data-testid="review-controls">
      {decided && !reopened && (
        <div className="review-verdict" data-testid="review-verdict">
          <span
            className={`verdict-badge verdict-${resolution === "APPROVED" ? "approved" : "rejected"}`}
          >
            {resolution === "APPROVED" ? "Approved" : "Rejected"}
          </span>
          {remarks ? <span className="verdict-remarks">“{remarks}”</span> : null}
          <button
            type="button"
            className="verdict-change"
            onClick={() => setReopened(true)}
            aria-label="Change verdict"
          >
            <RotateCcw size={12} /> Change verdict
          </button>
        </div>
      )}

      {showButtons && (
        <>
          <div className="review-row">
            <span className="review-label">Verdict</span>
            <button
              type="button"
              className="review-btn review-approve"
              disabled={pending !== null}
              onClick={() => submit(true)}
            >
              {pending === "approve" ? <Loader2 size={11} className="spin" /> : <ThumbsUp size={11} />}
              Approve
            </button>
            <button
              type="button"
              className="review-btn review-reject"
              disabled={pending !== null}
              onClick={() => submit(false)}
            >
              {pending === "reject" ? <Loader2 size={11} className="spin" /> : <ThumbsDown size={11} />}
              Reject
            </button>
          </div>
          <input
            className="review-remarks"
            placeholder="Remark (optional)"
            value={draftRemarks}
            onChange={(e) => setDraftRemarks(e.target.value)}
            aria-label="Review remarks"
          />
        </>
      )}

      {error && (
        <div className="review-error" role="alert" data-testid="review-error">
          {error}
        </div>
      )}

      <style>{`
        /* This renders in the left workspace panel, a flexlayout tabset the user can drag down to
           a 220px floor -- roughly 138px of content inside a finding card. Every rule below that
           looks defensive is load-bearing at that width.

           This block used to carry flex:0 0 100% to force its own line, back when it was
           appended as a fourth child of the card's Dismiss/Correct row. That never worked: the
           parent row was not flex-wrap:wrap, and a 100%-basis item in a nowrap row does not wrap,
           it overflows -- straight into the panel's overflow-x:hidden, which clipped "Approve" to
           "Ap". It is now a direct child of the card's column flex, so plain width:100% is both
           correct and sufficient. Do not reintroduce the flex-basis hack. */
        .review-controls {
          width: 100%;
          min-width: 0;
          box-sizing: border-box;
          margin-top: 6px;
          padding-top: 6px;
          border-top: 1px dashed var(--border-color);
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .review-row {
          display: flex; align-items: center; gap: 4px; flex-wrap: wrap; min-width: 0;
        }
        /* Own line, so the two buttons always get the full row width to divide. */
        .review-label {
          flex: 0 0 100%;
          font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
          text-transform: uppercase; color: var(--text-secondary);
        }
        .review-remarks {
          width: 100%; box-sizing: border-box; min-width: 0;
          font-size: 11px; font-family: inherit;
          padding: 3px 6px; border-radius: 4px;
          border: 1px solid var(--border-color);
          background: var(--bg-input, rgba(0, 0, 0, 0.15));
          color: var(--text-primary);
        }
        /* min-width:fit-content, NOT 0. With white-space:nowrap, min-width:0 lets a button shrink
           below its own label and the text is simply cut off -- that is the "Ap" bug. Refusing to
           shrink past the label means the row's flex-wrap:wrap moves the button to its own line
           instead, which is legible at any width. */
        .review-btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          flex: 1 1 auto;
          min-width: fit-content;
          white-space: nowrap;
          gap: 4px;
          font-size: 11px;
          font-weight: 600;
          padding: 3px 8px;
          border-radius: 6px;
          border: 1px solid var(--border-color);
          background: transparent;
          color: var(--text-primary);
          cursor: pointer;
        }
        .review-btn:disabled { opacity: 0.55; cursor: default; }
        .review-approve:hover:not(:disabled) {
          border-color: #10b981; color: #10b981;
        }
        .review-reject:hover:not(:disabled) {
          border-color: #ef4444; color: #ef4444;
        }
        .review-verdict {
          width: 100%; min-width: 0; box-sizing: border-box;
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          font-size: 12px;
        }
        .verdict-badge {
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 999px;
          border: 1px solid currentColor;
        }
        .verdict-approved { color: #10b981; }
        .verdict-rejected { color: #ef4444; }
        .verdict-remarks { color: var(--text-secondary); font-style: italic; overflow-wrap: anywhere; min-width: 0; }
        .verdict-change {
          display: inline-flex; align-items: center; gap: 4px;
          background: none; border: none; padding: 0;
          color: var(--text-secondary); cursor: pointer;
          font-size: 11px; text-decoration: underline;
        }
        .review-error { font-size: 11px; color: #ef4444; }
        .spin { animation: review-spin 1s linear infinite; }
        @keyframes review-spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

export default ReviewControls;
