import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import { X, AlertTriangle, AlertCircle, Info, Loader2 } from "lucide-react";
import { Button } from "./Button";

export type ConfirmModalVariant = "danger" | "warning" | "info";

export interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title?: string;
  message: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: ConfirmModalVariant;
  isLoading?: boolean;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title = "Confirm Action",
  message,
  confirmText = "CONFIRM",
  cancelText = "CANCEL",
  variant = "danger",
  isLoading = false,
}) => {
  // Close on Escape key
  useEffect(() => {
    if (!isOpen || isLoading) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  // Lock body scroll
  useEffect(() => {
    if (!isOpen) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const iconVariants = {
    danger: {
      icon: <AlertTriangle size={24} className="text-rose-500" />,
      boxBg: "bg-rose-500/10 border-rose-500/30",
      btnClass: "bg-rose-600 hover:bg-rose-700 text-white shadow-rose-600/20",
    },
    warning: {
      icon: <AlertCircle size={24} className="text-amber-500" />,
      boxBg: "bg-amber-500/10 border-amber-500/30",
      btnClass: "bg-amber-600 hover:bg-amber-700 text-white shadow-amber-600/20",
    },
    info: {
      icon: <Info size={24} className="text-accent-cyan" />,
      boxBg: "bg-accent-cyan/10 border-accent-cyan/30",
      btnClass: "bg-accent-cyan hover:bg-accent-cyan/80 text-zinc-950 shadow-accent-cyan/20",
    },
  };

  const currentVariant = iconVariants[variant] || iconVariants.danger;

  return createPortal(
    <div
      className="fixed inset-0 z-[100020] flex items-center justify-center modal-backdrop p-6 animate-in fade-in duration-150 select-none"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !isLoading) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-bg-card border-2 border-border-color shadow-2xl w-full max-w-lg p-8 md:p-9 text-text-primary flex flex-col gap-6 relative rounded-none animate-in zoom-in-95 duration-150">
        {/* Top-Right Red Close Button */}
        <button
          onClick={onClose}
          disabled={isLoading}
          className="absolute top-5 right-5 text-rose-500 hover:text-rose-600 hover:bg-rose-500/10 p-1.5 transition-colors cursor-pointer rounded-none disabled:opacity-50"
          title="Close"
        >
          <X size={20} />
        </button>

        {/* Header with Icon */}
        <div className="flex items-center gap-4 border-b border-border-color pb-5">
          <div
            className={`w-12 h-12 border flex items-center justify-center shrink-0 rounded-none ${currentVariant.boxBg}`}
          >
            {currentVariant.icon}
          </div>
          <div className="flex flex-col min-w-0">
            <h2 className="text-base md:text-lg font-black tracking-wider uppercase text-text-primary font-mono truncate">
              {title}
            </h2>
            <span className="text-[11px] font-mono uppercase tracking-widest text-text-muted">
              Confirmation Required
            </span>
          </div>
        </div>

        {/* Content / Message */}
        <div className="text-sm text-text-secondary leading-relaxed font-sans">
          {typeof message === "string" ? <p>{message}</p> : message}
        </div>

        {/* Actions Footer */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-border-color">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={isLoading}
            className="rounded-none font-mono font-bold text-xs uppercase px-5 py-2.5 cursor-pointer"
          >
            {cancelText}
          </Button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-6 py-2.5 rounded-none font-mono font-bold text-xs uppercase transition-all shadow-lg flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${currentVariant.btnClass}`}
          >
            {isLoading && <Loader2 size={14} className="animate-spin" />}
            <span>{confirmText}</span>
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
