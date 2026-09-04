import React from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Check } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
}

export const Select: React.FC<SelectProps> = ({ value, onChange, options, placeholder = "Select...", className = "" }) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const [rect, setRect] = React.useState<{ top: number; left: number; width: number } | null>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const listRef = React.useRef<HTMLDivElement>(null);

  const updateRect = React.useCallback(() => {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setRect({ top: r.bottom + 6, left: r.left, width: r.width });
  }, []);

  React.useEffect(() => {
    if (!isOpen) return;
    updateRect();

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (listRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    window.addEventListener("resize", updateRect);
    window.addEventListener("scroll", updateRect, true);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
      window.removeEventListener("resize", updateRect);
      window.removeEventListener("scroll", updateRect, true);
    };
  }, [isOpen, updateRect]);

  const selected = options.find((o) => o.value === value);

  return (
    <div className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 bg-bg-sidebar border border-border-color rounded-sm py-1.5 px-2.5 text-xs font-semibold text-text-primary hover:border-accent-cyan/50 focus:outline-none focus:border-accent-cyan transition-all cursor-pointer"
      >
        <span className={selected ? "text-text-primary" : "text-text-muted font-medium"}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown
          size={14}
          className={`text-text-muted transition-transform duration-150 shrink-0 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && rect && createPortal(
        <div
          ref={listRef}
          style={{ position: "fixed", top: rect.top, left: rect.left, width: rect.width, zIndex: 9999 }}
          className="bg-bg-card border border-border-color rounded-sm shadow-xl overflow-hidden"
        >
          <div className="max-h-60 overflow-y-auto py-1">
            {options.length === 0 && (
              <div className="px-3.5 py-2.5 text-xs text-text-muted">No options available</div>
            )}
            {options.map((opt) => (
              <button
                type="button"
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between gap-2 text-left px-3.5 py-2.5 text-xs font-semibold transition-colors ${
                  opt.value === value
                    ? "text-accent-cyan bg-accent-cyan/10"
                    : "text-text-primary hover:bg-sidebar-item-hover"
                }`}
              >
                <span className="truncate">{opt.label}</span>
                {opt.value === value && <Check size={13} className="shrink-0" />}
              </button>
            ))}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};
