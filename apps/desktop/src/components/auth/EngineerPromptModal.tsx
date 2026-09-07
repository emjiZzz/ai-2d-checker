import React, { useState, useEffect, useRef } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Check, X, ShieldAlert, ChevronDown, ShieldCheck } from "lucide-react";
import { useEngineerStore } from "../../stores/engineerStore";
import kmtiLogo from "../../assets/kmti_logo.png";
import { Button } from "../ui/Button";

const ENGINEER_PRESETS = [
  "CJ", "Erik", "Janzen", "JC", "Jenie",
  "Jethro", "Jonathan", "Joyce", "Kerby", "Lito",
  "Lorie", "Mariz", "Matt", "Mennjo", "MG",
  "Michael", "Nyl", "Raysan", "Sai", "Shela",
  "Zoren"
];

interface PolicyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccept: () => void;
}

const PolicyModal: React.FC<PolicyModalProps> = ({ isOpen, onClose, onAccept }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100010] flex items-center justify-center bg-black/85 p-6 animate-in fade-in duration-150 select-none">
      <div className="bg-bg-card border-2 border-border-color shadow-2xl w-full max-w-2xl p-8 text-text-primary flex flex-col gap-6 relative rounded-none animate-in zoom-in-95 duration-150">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-text-muted hover:text-text-primary p-2 transition-colors cursor-pointer"
          title="Close Policy"
        >
          <X size={22} />
        </button>

        <div className="flex items-center gap-4 border-b border-border-color pb-4">
          <div className="w-12 h-12 bg-accent-cyan/15 border border-accent-cyan/40 flex items-center justify-center shrink-0 rounded-none">
            <ShieldCheck size={26} className="text-accent-cyan" />
          </div>
          <div>
            <h3 className="text-lg font-bold tracking-wide uppercase text-text-primary font-mono">
              Terms of Evaluation & Data Policy
            </h3>
            <p className="text-sm text-text-muted">KMTI Engineering CAD Verification Platform</p>
          </div>
        </div>

        <div className="flex flex-col gap-4 text-sm text-text-muted leading-relaxed max-h-[60vh] overflow-y-auto pr-2">
          <div className="p-4 bg-bg-dark border border-border-color">
            <h4 className="text-sm font-bold text-text-primary uppercase tracking-wide mb-1.5 flex items-center gap-2">
              <span className="w-2 h-2 bg-accent-cyan inline-block"></span>
              1. Ground Truth & Annotation Collection
            </h4>
            <p className="text-xs leading-relaxed text-text-secondary">
              This evaluation build is configured for engineering verification, discrepancy identification, and ground-truth benchmarking. All coordinate markings, severity classifications, and reviewer notes are captured to calibrate quality baselines.
            </p>
          </div>

          <div className="p-4 bg-bg-dark border border-border-color">
            <h4 className="text-sm font-bold text-text-primary uppercase tracking-wide mb-1.5 flex items-center gap-2">
              <span className="w-2 h-2 bg-accent-cyan inline-block"></span>
              2. Centralized Database Synchronization
            </h4>
            <p className="text-xs leading-relaxed text-text-secondary">
              Review sessions and markings are synchronized to the organization's central MongoDB Atlas cluster under your designated engineer identifier. Offline evaluations are queued locally and pushed automatically upon network connection.
            </p>
          </div>

          <div className="p-4 bg-bg-dark border border-border-color">
            <h4 className="text-sm font-bold text-text-primary uppercase tracking-wide mb-1.5 flex items-center gap-2">
              <span className="w-2 h-2 bg-accent-cyan inline-block"></span>
              3. Vector Data Security & Intellectual Property
            </h4>
            <p className="text-xs leading-relaxed text-text-secondary">
              Proprietary CAD files (.dwg / .dxf) remain strictly protected and processed within the local secure sandbox environment. No raw engineering drawings are distributed to unauthorized third parties.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-border-color mt-2">
          <span className="text-xs text-text-muted">Please confirm your understanding of the evaluation terms.</span>
          <Button
            variant="primary"
            onClick={onAccept}
            className="px-7 py-3 text-sm font-bold uppercase tracking-wider rounded-none shadow-md cursor-pointer font-mono"
          >
            I Understand & Agree
          </Button>
        </div>
      </div>
    </div>
  );
};

export const EngineerPromptModal: React.FC = () => {
  const { engineerName, isModalOpen, setEngineerName, setIsModalOpen } = useEngineerStore();
  const [inputValue, setInputValue] = useState<string>(engineerName || "");
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [agreedToPolicy, setAgreedToPolicy] = useState<boolean>(Boolean(engineerName));
  const [isPolicyModalOpen, setIsPolicyModalOpen] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (engineerName) {
      setInputValue(engineerName);
      setAgreedToPolicy(true);
    }
  }, [engineerName]);

  // Click outside listener to close dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!isModalOpen) return null;

  const handleSelectPreset = (preset: string) => {
    setInputValue(preset);
    setIsDropdownOpen(false);
    if (error) setError("");
  };

  const handleExitApp = async () => {
    try {
      await getCurrentWindow().close();
    } catch {
      window.close();
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const finalName = inputValue.trim();

    if (!finalName) {
      setError("Please enter your name or select one from the list.");
      return;
    }
    if (!agreedToPolicy) {
      setError("Please acknowledge and accept the Terms of Evaluation & Data Policy.");
      return;
    }

    setError("");
    setEngineerName(finalName);
  };

  const handleDismissIfAlreadySet = () => {
    if (!engineerName.trim()) {
      handleExitApp();
      return;
    }
    setIsModalOpen(false);
  };

  return (
    <>
      {/* Solid Opaque Backdrop (Hides workspace completely for clean presentation) */}
      <div className="fixed inset-0 z-[100000] flex items-center justify-center bg-bg-dark p-6 animate-in fade-in duration-150 select-none">

        {/* Large, High-Legibility Enterprise CAD Container */}
        <div className="bg-bg-card border-2 border-border-color shadow-2xl w-full max-w-xl p-8 md:p-10 text-text-primary flex flex-col gap-6 relative rounded-none animate-in zoom-in-95 duration-150">

          {/* Top-Right Red Close / Exit Button */}
          <button
            onClick={handleDismissIfAlreadySet}
            className="absolute top-5 right-5 text-rose-500 hover:text-rose-600 hover:bg-rose-500/10 p-1.5 transition-colors cursor-pointer rounded-none"
            title={engineerName ? "Close" : "Exit Application"}
          >
            <X size={22} />
          </button>

          {/* Header with Clean KMTI Branding */}
          <div className="flex items-center gap-4 border-b border-border-color pb-5">
            <img src={kmtiLogo} alt="KMTI Logo" className="w-12 h-12 object-contain shrink-0" />
            <div className="flex flex-col">
              <h2 className="text-lg md:text-xl font-black tracking-wide text-text-primary font-mono">
                DraftCheck (Prototype)
              </h2>
              <p className="text-sm text-text-muted mt-0.5">
                Data Collection and Model Training for 2D CAD dxf files
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {/* Unified Input Combobox */}
            <div className="flex flex-col gap-2 relative" ref={dropdownRef}>
              <div className="flex items-center justify-between">
                <label className="text-xs md:text-sm font-bold uppercase tracking-wider text-text-secondary font-mono">
                  Tester Name
                </label>
                <span className="text-xs font-normal text-accent-cyan uppercase tracking-wider font-mono">
                  Required
                </span>
              </div>

              <div className="relative flex items-center">
                <input
                  type="text"
                  autoFocus
                  placeholder="Enter your name or select from the list"
                  value={inputValue}
                  onChange={(e) => {
                    setInputValue(e.target.value);
                    if (error) setError("");
                  }}
                  onFocus={() => setIsDropdownOpen(true)}
                  className="w-full bg-transparent border border-border-color px-4 py-3 text-sm md:text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-text-primary transition-colors rounded-none pr-12 font-medium"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                  className="absolute right-0 top-0 bottom-0 px-3.5 flex items-center justify-center text-text-muted hover:text-text-primary transition-colors cursor-pointer border-l border-border-color bg-transparent"
                  title="Show Preset List"
                >
                  <ChevronDown size={18} className={`transition-transform duration-150 ${isDropdownOpen ? "rotate-180 text-text-primary" : ""}`} />
                </button>
              </div>

              {/* Preset Dropdown Menu */}
              {isDropdownOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-bg-card border border-border-color shadow-xl z-50 max-h-56 overflow-y-auto rounded-none animate-in fade-in duration-100 divide-y divide-border-color/30">
                  <div className="px-4 py-2 bg-bg-sidebar text-xs font-mono font-bold text-text-muted uppercase tracking-wider">
                    Tester List
                  </div>
                  {ENGINEER_PRESETS.map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => handleSelectPreset(preset)}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between cursor-pointer ${inputValue === preset
                        ? "bg-bg-dark text-text-primary font-bold"
                        : "text-text-secondary hover:bg-bg-dark hover:text-text-primary"
                        }`}
                    >
                      <span>{preset}</span>
                      {inputValue === preset && <Check size={16} className="text-text-primary" />}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-xs text-text-muted mt-1">
                Your participation is a big help to train the model for making it better. Thank you for your contribution.
              </p>
            </div>

            {/* Terms & Agreement Checkbox */}
            <div className="pt-3 border-t border-border-color">
              <label className="flex items-start gap-3 cursor-pointer text-sm select-none">
                <input
                  type="checkbox"
                  checked={agreedToPolicy}
                  onChange={(e) => {
                    setAgreedToPolicy(e.target.checked);
                    if (error) setError("");
                  }}
                  className="mt-0.5 accent-accent-cyan cursor-pointer w-4 h-4"
                />
                <span className="text-xs md:text-sm text-text-secondary leading-snug">
                  I agree to the{" "}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsPolicyModalOpen(true);
                    }}
                    className="text-accent-cyan underline hover:text-accent-cyan/80 font-bold inline-flex items-center gap-0.5 cursor-pointer"
                  >
                    <span>Terms of Evaluation & Data Policy</span>
                  </button>
                  .
                </span>
              </label>
            </div>

            {error && (
              <div className="flex items-center gap-2.5 p-3 bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs md:text-sm font-semibold rounded-none">
                <ShieldAlert size={16} className="shrink-0 text-rose-400" />
                <span>{error}</span>
              </div>
            )}

            {/* Action Footer */}
            <div className="pt-3 border-t border-border-color mt-1">
              <Button
                type="submit"
                variant="primary"
                className="w-half flex items-center justify-center gap-2 py-3.5 text-xs md:text-sm font-bold uppercase tracking-wider rounded-none shadow-md transition-all font-mono cursor-pointer"
              >
                <span>PROCEED</span>
              </Button>
            </div>
          </form>
        </div>
      </div>

      {/* Dedicated Policy Modal */}
      <PolicyModal
        isOpen={isPolicyModalOpen}
        onClose={() => setIsPolicyModalOpen(false)}
        onAccept={() => {
          setAgreedToPolicy(true);
          if (error) setError("");
          setIsPolicyModalOpen(false);
        }}
      />
    </>
  );
};
