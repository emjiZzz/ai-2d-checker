import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import {
  ArrowRight,
  ArrowLeft,
  Check,
  X,
  Info,
  FolderPlus
} from "lucide-react";
import { useOnboardingStore, TOUR_STEPS } from "../../stores/onboardingStore";
import { useRoomStore } from "../../stores/roomStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useRooms } from "../../hooks/useRooms";
import { isPrototypeMode } from "../../config/features";
import { useIsEngineerPromptBlocking } from "../../stores/engineerStore";
import { Button } from "./Button";
import { isAuthFailure } from "../../services/fetchUtils";

/**
 * What to show when the Tutorial Room could not be created.
 *
 * Exported and pure so the wording can be tested without mounting the overlay, which needs the
 * room, onboarding and connection stores just to render.
 *
 * The auth branch used to be selected by regexing the message for a status code or the word
 * "unauthorised". The backend's actual detail is *"Access Denied: Invalid security API Token."* --
 * no code, none of those words -- so the branch written for this exact failure never fired, and
 * the installed 0.1.8 build showed the tester the raw backend string with no next step.
 * `isAuthFailure` reads the status off the thrown `ApiError` instead of inferring it from prose.
 */
export function describeRoomCreationFailure(err: unknown): string {
  if (isAuthFailure(err)) {
    return (
      "Not authorised by the backend, so the Tutorial Room was not created. The app is sending an " +
      "API token the backend does not recognise - restart the app, and if that does not clear it, " +
      "check the backend service is running."
    );
  }
  const message = err instanceof Error ? err.message : String(err);
  return "Could not create the Tutorial Room: " + message;
}

export const InteractiveTourOverlay: React.FC = () => {
  const { isTourActive, currentStep, nextStep, prevStep, goToStep, endTour } = useOnboardingStore();
  const { openRoom } = useRoomStore();
  const { rooms, createRoom } = useRooms();

  const oldDrawing = useWorkspaceStore((s) => s.oldDrawing);
  const newDrawing = useWorkspaceStore((s) => s.newDrawing);

  // Read up here with the other hooks, not beside the early return that uses it — the returns
  // below are conditional and a hook after one of them would change hook order between renders.
  const engineerPromptBlocking = useIsEngineerPromptBlocking();

  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [isCreatingRoom, setIsCreatingRoom] = useState(false);
  //: Why the Tutorial Room could not be created. Shown in the card; blocks the step.
  const [roomError, setRoomError] = useState("");
  const cardRef = useRef<HTMLDivElement>(null);

  const step = TOUR_STEPS[currentStep];

  // Measure and track target bounding box
  useEffect(() => {
    if (!isTourActive || !step) {
      setTargetRect(null);
      return;
    }

    const updateRect = () => {
      const el = document.querySelector(step.targetSelector);
      if (el) {
        setTargetRect(el.getBoundingClientRect());
      } else {
        setTargetRect(null);
      }
    };

    updateRect();

    // Re-measure on resize, scroll, or DOM mutation
    window.addEventListener("resize", updateRect);
    window.addEventListener("scroll", updateRect, true);

    const interval = setInterval(updateRect, 300);

    return () => {
      window.removeEventListener("resize", updateRect);
      window.removeEventListener("scroll", updateRect, true);
      clearInterval(interval);
    };
  }, [isTourActive, currentStep, step]);

  // Keyboard navigation
  useEffect(() => {
    if (!isTourActive) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        endTour();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isTourActive, endTour]);

  /**
   * Defence in depth for the identity prompt.
   *
   * `RoomsView` already refuses to *start* the tour while the prompt is up, which is the real
   * fix. This covers the paths that do not go through that effect: the prompt being reopened
   * mid-tour, and the "Quick Tour" button being pressed by anything other than a resolved user.
   *
   * Needed because the two cannot be reconciled by stacking order. The prompt's backdrop is
   * `z-[100000]` and opaque on purpose ("Hides workspace completely for clean presentation");
   * this overlay is `z-[999999]`. Whoever is on top, one of them is a modal drawn over another
   * modal — so the answer has to be that only one of them renders.
   */
  if (engineerPromptBlocking) return null;

  if (!isTourActive || !step) return null;

  // Handle Step 1 Next: Auto create/open "Tutorial Room"
  const handleNextClick = async () => {
    if (currentStep === 0) {
      setIsCreatingRoom(true);
      try {
        // Look for existing "Tutorial Room"
        const existing = rooms.find((r) => r.name.toLowerCase() === "tutorial room");
        if (existing) {
          await openRoom(existing.id);
        } else {
          const newRoom = await createRoom({
            name: "Tutorial Room",
            room_mode: isPrototypeMode() ? "manual_check" : "ai_comparison",
          });
          if (newRoom?.id) {
            await openRoom(newRoom.id);
          }
        }
        setRoomError("");
        nextStep();
      } catch (err) {
        /*
          🔴 This used to be `console.error(...); nextStep();` -- it advanced the tour ANYWAY.

          So "Enter Tutorial Room" moved to step 2 ("Upload Reference Drawing") while no room had
          been created and the page behind still read "NO WORKSPACES YET". The tour then walked
          the tester through five more steps against a room that did not exist. Reported from the
          installed 0.1.2 build; the backend log shows the POST /api/v1/rooms answering 401 at the
          exact moment the step advanced.

          Advancing past a failed prerequisite is worse than a visible error: the console line was
          real, and nobody has a console open in a packaged desktop app.
        */
        setRoomError(describeRoomCreationFailure(err));
      } finally {
        setIsCreatingRoom(false);
      }
      return;
    }

    nextStep();
  };

  const isNextDisabled =
    isCreatingRoom ||
    (currentStep === 1 && !oldDrawing) ||
    (currentStep === 2 && !newDrawing);

  // Calculate popover positioning
  const getPopoverStyle = (): React.CSSProperties => {
    if (step.position === "top") {
      return {
        top: "32px",
        left: "50%",
        transform: "translateX(-50%)",
        position: "fixed",
      };
    }

    if (!targetRect) {
      return {
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        position: "fixed",
      };
    }

    const padding = 16;
    const cardWidth = 440;
    const { top, left, right, bottom, width } = targetRect;

    // Prefer below target
    if (bottom + 260 < window.innerHeight) {
      return {
        top: `${bottom + padding}px`,
        left: `${Math.max(20, Math.min(window.innerWidth - cardWidth - 20, left + width / 2 - cardWidth / 2))}px`,
        position: "fixed",
      };
    }

    // Otherwise above target
    if (top - 280 > 0) {
      return {
        top: `${Math.max(20, top - 260 - padding)}px`,
        left: `${Math.max(20, Math.min(window.innerWidth - cardWidth - 20, left + width / 2 - cardWidth / 2))}px`,
        position: "fixed",
      };
    }

    // Default right / left
    if (right + cardWidth + 20 < window.innerWidth) {
      return {
        top: `${Math.max(20, top)}px`,
        left: `${right + padding}px`,
        position: "fixed",
      };
    }

    return {
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      position: "fixed",
    };
  };

  return createPortal(
    <div className="fixed inset-0 z-[999999] pointer-events-none select-none">
      {/* ── Spotlight Glowing Target Frame with Outer Backdrop Shadow ── */}
      {targetRect ? (
        <div
          className="absolute pointer-events-none transition-all duration-200 border-2 border-accent-cyan shadow-[0_0_24px_rgba(0,229,255,0.45)]"
          style={{
            top: `${Math.max(0, targetRect.top - 4)}px`,
            left: `${Math.max(0, targetRect.left - 4)}px`,
            width: `${targetRect.width + 8}px`,
            height: `${targetRect.height + 8}px`,
            boxShadow: "0 0 0 9999px rgba(5, 10, 20, 0.78)",
          }}
        >
          {/* Cyan Corner Highlights */}
          <span className="absolute -top-1 -left-1 w-2.5 h-2.5 bg-accent-cyan" />
          <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-accent-cyan" />
          <span className="absolute -bottom-1 -left-1 w-2.5 h-2.5 bg-accent-cyan" />
          <span className="absolute -bottom-1 -right-1 w-2.5 h-2.5 bg-accent-cyan" />
        </div>
      ) : (
        <div className="fixed inset-0 bg-[rgba(5,10,20,0.78)] pointer-events-none" />
      )}

      {/* ── Floating Guidance Tooltip Card ── */}
      <div
        ref={cardRef}
        style={getPopoverStyle()}
        className="w-[440px] max-w-[calc(100vw-32px)] bg-bg-card border-2 border-accent-cyan shadow-2xl flex flex-col z-[1000000] pointer-events-auto animate-in fade-in zoom-in-95 duration-150"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-bg-sidebar border-b border-border-color">
          <div>
            <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-accent-cyan">
              {step.badge}
            </span>
          </div>
          <button
            onClick={endTour}
            className="text-text-muted hover:text-rose-400 p-0.5 transition-colors cursor-pointer"
            title="Exit Tour (Esc)"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 flex flex-col gap-2.5">
          <h3 className="text-sm font-mono font-bold text-text-primary">
            {step.title}
          </h3>
          <p className="text-xs text-text-secondary leading-relaxed font-sans">
            {step.description}
          </p>

          {/* Practical Tester Tip Box */}
          <div className="flex items-start gap-2 bg-bg-dark border border-border-color p-2.5 mt-1">
            <Info size={14} className="text-accent-cyan shrink-0 mt-0.5" />
            <p className="text-[11px] font-mono text-text-muted leading-tight">
              {step.tips}
            </p>
          </div>

          {/*
            Why the step could not complete. The tour STAYS on this step when this is set — the
            alternative, which shipped, was advancing to "Upload Reference Drawing" with no room
            to upload into.
          */}
          {roomError && (
            <div
              role="alert"
              className="px-2.5 py-2 border border-rose-500/40 bg-rose-500/10 text-[11px] leading-relaxed text-rose-300"
            >
              {roomError}
            </div>
          )}
        </div>

        {/* Footer with Controls */}
        <div className="px-4 py-2.5 bg-bg-sidebar/80 border-t border-border-color flex items-center justify-between">
          {/* Step Dots */}
          <div className="flex items-center gap-1.5">
            {TOUR_STEPS.map((s, idx) => (
              <button
                key={s.stepIndex}
                onClick={() => goToStep(idx)}
                title={s.title}
                className={`h-1.5 transition-all cursor-pointer ${
                  idx === currentStep
                    ? "w-6 bg-accent-cyan"
                    : "w-1.5 bg-border-color hover:bg-text-muted"
                }`}
              />
            ))}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={endTour}
              className="rounded-none font-mono text-[11px] uppercase px-2.5 h-7 text-text-muted hover:text-text-primary cursor-pointer"
            >
              Skip
            </Button>
            {currentStep > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={prevStep}
                className="rounded-none font-mono text-[11px] uppercase px-2.5 h-7 gap-1 cursor-pointer"
              >
                <ArrowLeft size={11} />
                <span>Back</span>
              </Button>
            )}
            <Button
              variant="primary"
              size="sm"
              onClick={handleNextClick}
              disabled={isNextDisabled}
              className="rounded-none font-mono font-bold text-[11px] uppercase px-3.5 h-7 gap-1.5 cursor-pointer disabled:opacity-50"
              title={
                currentStep === 1 && !oldDrawing
                  ? "Upload a reference drawing to proceed"
                  : currentStep === 2 && !newDrawing
                  ? "Upload a revision drawing to proceed"
                  : undefined
              }
            >
              {currentStep === 0 ? (
                <>
                  <FolderPlus size={12} />
                  <span>{isCreatingRoom ? "Opening Room..." : "Enter Tutorial Room"}</span>
                </>
              ) : currentStep === 1 ? (
                <>
                  <span>Next: Revision Drawing</span>
                  <ArrowRight size={12} />
                </>
              ) : currentStep === 2 ? (
                <>
                  <span>Next: Left-Click Status</span>
                  <ArrowRight size={12} />
                </>
              ) : currentStep === 3 ? (
                <>
                  <span>Next: Right-Click Actions</span>
                  <ArrowRight size={12} />
                </>
              ) : currentStep === 4 ? (
                <>
                  <span>Next: Results Panel</span>
                  <ArrowRight size={12} />
                </>
              ) : (
                <>
                  <span>Finish Tour</span>
                  <Check size={12} />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};
