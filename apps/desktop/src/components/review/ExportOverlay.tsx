import { createPortal } from "react-dom";
import { FileText, Loader2, Check } from "lucide-react";

/**
 * A blocking veil over the whole app while a PDF export runs. Owner's call, 2026-08-25.
 *
 * The export is **not** a background task, and the button alone said otherwise. It takes ~17 s on
 * a dense sheet, the checklist rasterises on the MAIN THREAD so the window is genuinely
 * unresponsive for part of it, and a disabled button that reads "Building…" is easy to miss in a
 * toolbar. People clicked elsewhere, got nothing, and clicked Export again.
 *
 * ## Two things here are deliberate and easy to undo by accident
 *
 * **The titlebar stays live.** `AppHeader` is `z-[9999]`; this sits at `Z_INDEX` just below it, so
 * the window's own minimise / maximise / close keep working while everything under them is
 * covered. Raising this above the header traps the user in an app they cannot minimise for the
 * length of a 17-second render — and if the export ever hangs, cannot close either. It is keyed
 * off the header's z-index rather than a `top: 40px` offset so the two cannot drift apart when
 * the header's height changes.
 *
 * **It captures pointer events.** The sibling drag overlay in `App.tsx` sets `pointer-events-none`
 * because it is decoration over a drop target; this one must not. Blocking input IS the feature —
 * the store is being read to build the document, and a marking retracted halfway through produces
 * a report whose page 1 and page 2 disagree.
 *
 * Portalled to `document.body` so it is not clipped by the `overflow: hidden` panel whose toolbar
 * holds the button that started it.
 */
export const Z_INDEX = 9998;

interface StepItem {
  key: string;
  title: string;
  desc: string;
}

const STEPS: StepItem[] = [
  { key: "drawing", title: "CAD Drawing Sheet", desc: "Rendering vector paths & marking pins" },
  { key: "checklist", title: "Compliance Checklist", desc: "Compiling table rows & status tallies" },
  { key: "folder", title: "Save Destination", desc: "Selecting target export directory" },
  { key: "writing", title: "Write PDF Files", desc: "Packaging companion drawing & checklist PDFs" },
];

function getStepIndexAndProgress(phaseText: string | null | undefined): { stepIndex: number; progressPct: number } {
  if (!phaseText) return { stepIndex: 0, progressPct: 15 };
  const p = phaseText.toLowerCase();
  if (p.includes("drawing") || p.includes("rendering")) {
    return { stepIndex: 0, progressPct: 25 };
  }
  if (p.includes("checklist") || p.includes("building the checklist")) {
    return { stepIndex: 1, progressPct: 55 };
  }
  if (p.includes("folder") || p.includes("choose a folder") || p.includes("destination")) {
    return { stepIndex: 2, progressPct: 80 };
  }
  if (p.includes("writing") || p.includes("write")) {
    return { stepIndex: 3, progressPct: 95 };
  }
  return { stepIndex: 0, progressPct: 15 };
}

export function ExportOverlay({ active, phase }: { active: boolean; phase?: string | null }) {
  if (!active || typeof document === "undefined") return null;

  const { stepIndex, progressPct } = getStepIndexAndProgress(phase);

  return createPortal(
    <div
      role="alertdialog"
      aria-busy="true"
      aria-live="polite"
      aria-label="Building the compliance report"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: Z_INDEX,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(9, 11, 16, 0.65)",
        backdropFilter: "blur(4px)",
        cursor: "wait",
      }}
      // The veil is the point, but a click on it should not fall through to the canvas beneath.
      onClick={(event) => event.stopPropagation()}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 16,
          padding: "24px 28px",
          borderRadius: 8,
          background: "var(--bg-card)",
          border: "1.5px solid var(--accent-cyan)",
          boxShadow: "0 20px 50px rgba(0, 0, 0, 0.5)",
          width: 380,
          maxWidth: "92vw",
          textAlign: "left",
        }}
      >
        {/* Header with icon, title & progress bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              position: "relative",
              width: 36,
              height: 36,
              borderRadius: 6,
              background: "rgba(0, 229, 255, 0.12)",
              border: "1px solid rgba(0, 229, 255, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <FileText size={18} style={{ color: "var(--accent-cyan)" }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "var(--text-primary)",
                letterSpacing: "0.02em",
                lineHeight: 1.3,
              }}
            >
              Exporting Compliance Report
            </div>
            <div style={{ fontSize: 11, color: "var(--accent-cyan)", fontWeight: 600, marginTop: 2 }}>
              Step {stepIndex + 1} of {STEPS.length}: {STEPS[stepIndex]?.title}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div
          style={{
            width: "100%",
            height: 5,
            background: "var(--border-color)",
            borderRadius: 3,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${progressPct}%`,
              background: "linear-gradient(90deg, var(--accent-cyan) 0%, #10b981 100%)",
              borderRadius: 3,
              transition: "width 0.4s ease",
            }}
          />
        </div>

        {/* Stepper list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {STEPS.map((step, idx) => {
            const isCompleted = idx < stepIndex;
            const isCurrent = idx === stepIndex;
            const isPending = idx > stepIndex;

            return (
              <div
                key={step.key}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  opacity: isPending ? 0.45 : 1,
                  transition: "opacity 0.2s ease",
                }}
              >
                {/* Step indicator icon */}
                <div
                  style={{
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    marginTop: 1,
                    background: isCompleted
                      ? "#10b981"
                      : isCurrent
                      ? "rgba(0, 229, 255, 0.15)"
                      : "var(--sidebar-item-hover)",
                    border: isCompleted
                      ? "none"
                      : isCurrent
                      ? "1.5px solid var(--accent-cyan)"
                      : "1px solid var(--border-color)",
                    color: isCompleted ? "#fff" : isCurrent ? "var(--accent-cyan)" : "var(--text-muted)",
                    fontSize: 10,
                    fontWeight: 700,
                  }}
                >
                  {isCompleted ? (
                    <Check size={12} strokeWidth={3} />
                  ) : isCurrent ? (
                    <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
                  ) : (
                    idx + 1
                  )}
                </div>

                {/* Step info */}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: isCurrent ? 700 : 600,
                      color: isCurrent
                        ? "var(--text-primary)"
                        : isCompleted
                        ? "var(--text-secondary)"
                        : "var(--text-muted)",
                    }}
                  >
                    {step.title}
                  </div>
                  <div
                    style={{
                      fontSize: 10.5,
                      color: isCurrent ? "var(--accent-cyan)" : "var(--text-muted)",
                      marginTop: 1,
                    }}
                  >
                    {isCurrent && phase ? phase : step.desc}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer caption */}
        <div
          style={{
            fontSize: 10.5,
            color: "var(--text-muted)",
            borderTop: "1px solid var(--border-color)",
            paddingTop: 10,
            textAlign: "center",
          }}
        >
          {phase || "Preparing…"}
        </div>
      </div>

      {/* Spin animation for spinner icons */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>,
    document.body,
  );
}
