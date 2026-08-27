import { createPortal } from "react-dom";
import { FileText, Loader2 } from "lucide-react";

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

export function ExportOverlay({ active, phase }: { active: boolean; phase?: string | null }) {
  if (!active || typeof document === "undefined") return null;

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
        background: "rgba(9, 11, 16, 0.55)",
        backdropFilter: "blur(2px)",
        cursor: "wait",
      }}
      // The veil is the point, but a click on it should not fall through to the canvas beneath.
      onClick={(event) => event.stopPropagation()}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
          padding: "22px 28px",
          // Square corners, by the owner's call. Not an oversight to be "fixed" later.
          borderRadius: 0,
          background: "var(--bg-card)",
          border: "1px solid var(--accent-cyan)",
          boxShadow: "0 18px 50px rgba(0, 0, 0, 0.45)",
          maxWidth: 340,
          textAlign: "center",
        }}
      >
        <div style={{ position: "relative", width: 40, height: 40 }}>
          <Loader2
            size={40}
            aria-hidden
            style={{
              color: "var(--accent-cyan)",
              animation: "spin 1s linear infinite",
              position: "absolute",
              inset: 0,
            }}
          />
          <FileText
            size={16}
            aria-hidden
            style={{
              color: "var(--accent-cyan)",
              position: "absolute",
              top: 12,
              left: 12,
            }}
          />
        </div>

        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: "var(--text-primary)",
            letterSpacing: "0.02em",
          }}
        >
          Building the compliance report
        </div>

        {/* The phase, or a neutral line — never an empty gap that changes the card's height. */}
        <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
          {phase || "Preparing…"}
        </div>

        <div style={{ fontSize: 10, color: "var(--text-muted)", opacity: 0.75 }}>
          This can take a few seconds on a dense drawing.
        </div>
      </div>

      {/* `animate-spin` is a Tailwind class and this component is styled inline, so the keyframes
          come with it rather than depending on a utility that may not be in the build. */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>,
    document.body,
  );
}
