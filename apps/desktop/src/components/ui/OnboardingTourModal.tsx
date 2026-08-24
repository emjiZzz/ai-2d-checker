import React, { useState, useEffect } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Check,
  UploadCloud,
  SplitSquareVertical,
  PenTool,
  CheckCircle2
} from "lucide-react";
import { Modal } from "./Modal";
import { Button } from "./Button";

interface OnboardingTourModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface TourStep {
  stepNumber: number;
  badge: string;
  title: string;
  summary: string;
  points: { title: string; detail: string }[];
  graphic: React.ReactNode;
}

export const OnboardingTourModal: React.FC<OnboardingTourModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [currentStep, setCurrentStep] = useState(0);

  const steps: TourStep[] = [
    {
      stepNumber: 1,
      badge: "STEP 1 OF 4",
      title: "Upload Drawing Pair",
      summary: "Start by setting up your reference and revision drawings.",
      points: [
        {
          title: "Create a Room",
          detail: "Click '+ Create New' to create a workspace for your drawing check.",
        },
        {
          title: "Add Reference File",
          detail: "Upload the original or previous CAD drawing (DXF).",
        },
        {
          title: "Add Revision File",
          detail: "Upload the new updated CAD drawing that needs inspection.",
        },
      ],
      graphic: (
        <div className="w-full h-full bg-bg-dark border border-border-color p-4 flex flex-col justify-center gap-3 select-none">
          <div className="flex items-center justify-between text-xs font-mono font-bold text-text-primary border-b border-border-color/60 pb-2">
            <div className="flex items-center gap-2">
              <UploadCloud size={16} className="text-accent-cyan" />
              <span>New Inspection Room</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="bg-bg-card p-2.5 border border-border-color flex flex-col gap-1">
              <span className="text-text-muted text-[10px]">Reference Drawing</span>
              <span className="text-text-primary font-semibold truncate">Base_RevA.dxf</span>
            </div>
            <div className="bg-bg-card p-2.5 border border-accent-cyan/60 flex flex-col gap-1">
              <span className="text-accent-cyan text-[10px]">Revision Drawing</span>
              <span className="text-accent-cyan font-semibold truncate">Updated_RevB.dxf</span>
            </div>
          </div>
        </div>
      ),
    },
    {
      stepNumber: 2,
      badge: "STEP 2 OF 4",
      title: "Compare Side-by-Side",
      summary: "Inspect and navigate both drawings simultaneously.",
      points: [
        {
          title: "Pan Around the Sheet",
          detail: "Hold Space and drag with your mouse (or use Middle-Click) to move.",
        },
        {
          title: "Zoom In & Out",
          detail: "Use your mouse scroll wheel to zoom in on fine details and dimensions.",
        },
        {
          title: "Synchronized View",
          detail: "Both drawings move together so you can easily spot differences.",
        },
      ],
      graphic: (
        <div className="w-full h-full bg-bg-dark border border-border-color p-4 flex flex-col justify-center gap-2 select-none">
          <div className="flex items-center justify-between text-xs font-mono pb-1 border-b border-border-color/60">
            <div className="flex items-center gap-1.5 text-text-muted">
              <SplitSquareVertical size={14} className="text-accent-cyan" />
              <span>Dual Workspace View</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 h-20 text-[10px] font-mono">
            <div className="bg-bg-card border border-border-color flex items-center justify-center text-text-muted">
              Reference View
            </div>
            <div className="bg-bg-card border border-accent-cyan/40 flex items-center justify-center text-accent-cyan font-semibold">
              Revision View
            </div>
          </div>
          <div className="text-[10px] font-mono text-center text-text-muted">
            Space + Drag to Pan • Scroll to Zoom
          </div>
        </div>
      ),
    },
    {
      stepNumber: 3,
      badge: "STEP 3 OF 4",
      title: "Mark Differences & Errors",
      summary: "Highlight any discrepancies you find on the revision drawing.",
      points: [
        {
          title: "Select Error Location",
          detail: "Click or draw a box on the drawing where a change or mistake is located.",
        },
        {
          title: "Describe the Issue",
          detail: "Choose the issue type (e.g. missing hole, dimension change, text error).",
        },
        {
          title: "Set Importance",
          detail: "Tag the issue as Critical, Major, or Minor to organize your findings.",
        },
      ],
      graphic: (
        <div className="w-full h-full bg-bg-dark border border-border-color p-4 flex flex-col justify-center gap-2.5 select-none">
          <div className="flex items-center justify-between text-xs font-mono pb-1 border-b border-border-color/60">
            <div className="flex items-center gap-1.5 text-text-muted">
              <PenTool size={14} className="text-accent-cyan" />
              <span>Marking Tool</span>
            </div>
          </div>
          <div className="bg-rose-500/10 border border-rose-500/50 p-2.5 flex items-start gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <div className="text-xs font-mono font-bold text-rose-400">Missing Cutout / Hole</div>
              <div className="text-[10px] font-mono text-text-muted">Marked on Revision • Critical</div>
            </div>
          </div>
        </div>
      ),
    },
    {
      stepNumber: 4,
      badge: "STEP 4 OF 4",
      title: "Save & Complete Check",
      summary: "Review your marked items and finish the inspection.",
      points: [
        {
          title: "Checklist Review",
          detail: "Review all your marked items in the checklist on the right panel.",
        },
        {
          title: "Save Progress",
          detail: "Your markings and notes are saved automatically as you work.",
        },
        {
          title: "Complete Inspection",
          detail: "Click 'Complete' to log your check result and return to your workspaces.",
        },
      ],
      graphic: (
        <div className="w-full h-full bg-bg-dark border border-border-color p-4 flex flex-col justify-center gap-2 select-none">
          <div className="flex items-center justify-between text-xs font-mono pb-1 border-b border-border-color/60">
            <div className="flex items-center gap-1.5 text-text-muted">
              <CheckCircle2 size={14} className="text-emerald-400" />
              <span>Checklist Summary</span>
            </div>
            <span className="text-emerald-400 font-bold">READY</span>
          </div>
          <div className="flex flex-col gap-1 text-[11px] font-mono">
            <div className="flex items-center gap-1.5 text-text-primary">
              <Check size={12} className="text-emerald-400" />
              <span>3 discrepancies marked</span>
            </div>
            <div className="flex items-center gap-1.5 text-text-primary">
              <Check size={12} className="text-emerald-400" />
              <span>Reference comparison verified</span>
            </div>
          </div>
          <div className="mt-1 bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan text-[11px] font-mono py-1 text-center font-bold">
            Complete Inspection
          </div>
        </div>
      ),
    },
  ];

  // Keyboard navigation (ArrowLeft, ArrowRight)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") {
        setCurrentStep((prev) => Math.min(steps.length - 1, prev + 1));
      } else if (e.key === "ArrowLeft") {
        setCurrentStep((prev) => Math.max(0, prev - 1));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, steps.length]);

  const step = steps[currentStep];

  const handleFinish = () => {
    localStorage.setItem("has_seen_onboarding_tour", "true");
    onClose();
  };

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep((prev) => prev + 1);
    } else {
      handleFinish();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep((prev) => prev - 1);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleFinish}
      title="How to Use AI 2D Drawing Checker"
      description="Learn the simple 4-step workflow to compare drawing revisions and mark errors."
      maxWidthClassName="max-w-2xl"
      footer={
        <div className="flex items-center justify-between w-full">
          {/* Step Progress Indicators */}
          <div className="flex items-center gap-1.5">
            {steps.map((s, idx) => (
              <button
                key={s.stepNumber}
                onClick={() => setCurrentStep(idx)}
                title={`Go to Step ${s.stepNumber}: ${s.title}`}
                className={`h-2 transition-all cursor-pointer rounded-none ${
                  idx === currentStep
                    ? "w-7 bg-accent-cyan"
                    : "w-2 bg-border-color hover:bg-text-muted"
                }`}
              />
            ))}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={handleFinish}
              className="rounded-none font-mono text-xs uppercase px-3 h-8 text-text-muted hover:text-text-primary cursor-pointer"
            >
              Skip
            </Button>
            {currentStep > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handlePrev}
                className="rounded-none font-mono text-xs uppercase px-3 h-8 gap-1 cursor-pointer"
              >
                <ArrowLeft size={13} />
                <span>Back</span>
              </Button>
            )}
            <Button
              variant="primary"
              size="sm"
              onClick={handleNext}
              className="rounded-none font-mono font-bold text-xs uppercase px-4 h-8 gap-1.5 cursor-pointer"
            >
              <span>{currentStep === steps.length - 1 ? "Start Checking" : "Next"}</span>
              {currentStep === steps.length - 1 ? <Check size={13} /> : <ArrowRight size={13} />}
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-5">
        {/* Step Header */}
        <div className="flex items-center justify-between pb-3 border-b border-border-color">
          <div>
            <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-accent-cyan">
              {step.badge}
            </span>
            <h3 className="text-base font-mono font-bold text-text-primary mt-0.5">
              {step.title}
            </h3>
            <p className="text-xs text-text-muted mt-0.5">
              {step.summary}
            </p>
          </div>
        </div>

        {/* Step Content: Graphic & Simple Bullet Points */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
          {/* Visual Diagram Box */}
          <div className="min-h-[160px] flex items-center justify-center">
            {step.graphic}
          </div>

          {/* Feature Bullet Points */}
          <div className="flex flex-col justify-center gap-3">
            {step.points.map((pt, i) => (
              <div key={i} className="flex flex-col gap-0.5">
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-accent-cyan shrink-0" />
                  <h4 className="text-xs font-mono font-bold text-text-primary">
                    {pt.title}
                  </h4>
                </div>
                <p className="text-[11px] text-text-muted leading-relaxed pl-3 font-sans">
                  {pt.detail}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
};
