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
  title = "CONFIRM ACTION",
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
      icon: <AlertTriangle size={18} className="text-rose-500" />,
      tag: "CRITICAL ACTION",
      tagClass: "text-rose-500 border-rose-500/30 bg-rose-500/10",
      btnClass: "bg-rose-600 hover:bg-rose-700 text-white shadow-rose-600/20",
    },
    warning: {
      icon: <AlertCircle size={18} className="text-amber-500" />,
      tag: "WARNING",
      tagClass: "text-amber-500 border-amber-500/30 bg-amber-500/10",
      btnClass: "bg-amber-600 hover:bg-amber-700 text-white shadow-amber-600/20",
    },
    info: {
      icon: <Info size={18} className="text-accent-cyan" />,
      tag: "NOTICE",
      tagClass: "text-accent-cyan border-accent-cyan/30 bg-accent-cyan/10",
      btnClass: "bg-accent-cyan hover:bg-accent-cyan/80 text-zinc-950 shadow-accent-cyan/20",
    },
  };

  const currentVariant = iconVariants[variant] || iconVariants.danger;

  return createPortal(
    <div
      className="fixed inset-0 z-[100020] flex items-center justify-center modal-backdrop p-4 animate-in fade-in duration-100 select-none"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !isLoading) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      {/* Compact Industrial CAD Dialog Box */}
      <div className="bg-bg-card border-2 border-border-color shadow-2xl w-full max-w-md text-text-primary flex flex-col rounded-none animate-in zoom-in-95 duration-100 overflow-hidden">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-bg-sidebar border-b border-border-color">
          <div className="flex items-center gap-2">
            {currentVariant.icon}
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-text-primary">
              {title}
            </span>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="text-text-muted hover:text-rose-500 p-1 transition-colors cursor-pointer rounded-none disabled:opacity-50"
            title="Cancel (Esc)"
          >
            <X size={16} />
          </button>
        </div>

        {/* Dialog Body */}
        <div className="p-5 flex flex-col gap-3.5">
          <div className="inline-flex self-start items-center px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider border rounded-none">
            <span className={currentVariant.tagClass}>{currentVariant.tag}</span>
          </div>

          <div className="text-xs text-text-secondary leading-relaxed font-sans">
            {typeof message === "string" ? <p>{message}</p> : message}
          </div>
        </div>

        {/* Action Controls */}
        <div className="px-4 py-3 bg-bg-sidebar/50 border-t border-border-color flex items-center justify-end gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={isLoading}
            className="rounded-none font-mono font-bold text-xs uppercase px-4 h-8 cursor-pointer"
          >
            {cancelText}
          </Button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-5 h-8 rounded-none font-mono font-bold text-xs uppercase transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${currentVariant.btnClass}`}
          >
            {isLoading && <Loader2 size={13} className="animate-spin" />}
            <span>{confirmText}</span>
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
