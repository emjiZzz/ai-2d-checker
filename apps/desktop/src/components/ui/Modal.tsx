import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "../../utils/cn";

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  icon?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Tailwind max-width class, e.g. "max-w-md" | "max-w-2xl" | "max-w-4xl". Defaults to max-w-lg. */
  maxWidthClassName?: string;
  /** Disable closing via backdrop click / Escape — use for destructive confirmations mid-flow. */
  disableDismiss?: boolean;
  className?: string;
}

/**
 * Global modal primitive. Renders into document.body via a portal so it is always
 * centered on the viewport regardless of where it's invoked from in the tree —
 * unlike the older per-page ".frosted-glass-overlay" pattern (see UserManagement.css),
 * which was `position: absolute` against a scrollable ancestor and could drift off-
 * screen on tall pages. New modals should use this instead of copy-pasting that CSS.
 */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  icon,
  description,
  children,
  footer,
  maxWidthClassName = "max-w-lg",
  disableDismiss = false,
  className,
}) => {
  useEffect(() => {
    if (!isOpen || disableDismiss) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, disableDismiss, onClose]);

  // Prevent background scroll while a modal is open.
  useEffect(() => {
    if (!isOpen) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !disableDismiss) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? "modal-title" : undefined}
    >
      <div
        className={cn(
          "w-full bg-bg-card border border-border-color rounded-2xl shadow-2xl animate-scale-up flex flex-col max-h-[90vh]",
          maxWidthClassName,
          className
        )}
      >
        {(title || !disableDismiss) && (
          <div className="flex items-start justify-between gap-4 px-8 py-6 border-b border-border-color shrink-0">
            <div>
              {title && (
                <h2
                  id="modal-title"
                  className="text-lg font-bold text-text-primary flex items-center gap-2.5"
                >
                  {icon}
                  {title}
                </h2>
              )}
              {description && (
                <p className="text-sm text-text-muted mt-1.5">{description}</p>
              )}
            </div>
            {!disableDismiss && (
              <button
                onClick={onClose}
                className="text-text-muted hover:text-text-primary hover:bg-white/5 rounded-md p-1.5 transition-all shrink-0 -mr-1.5 -mt-1.5"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            )}
          </div>
        )}

        <div className="px-8 py-7 overflow-y-auto">{children}</div>

        {footer && (
          <div className="px-8 py-5 shrink-0 border-t border-border-color bg-black/10 rounded-b-2xl">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};
