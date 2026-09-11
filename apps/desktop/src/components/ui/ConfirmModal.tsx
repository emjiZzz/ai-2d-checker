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
  confirmText = "Confirm",
  cancelText = "Cancel",
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

  const variantConfig = {
    danger: {
      icon: <AlertTriangle size={17} className="text-red-500 shrink-0" />,
      btnClass: "bg-red-600 hover:bg-red-700 text-white",
    },
    warning: {
      icon: <AlertCircle size={17} className="text-amber-500 shrink-0" />,
      btnClass: "bg-amber-600 hover:bg-amber-700 text-white",
    },
    info: {
      icon: <Info size={17} className="text-accent-cyan shrink-0" />,
      btnClass: "bg-accent-cyan hover:bg-accent-cyan/80 text-zinc-950",
    },
  };

  const current = variantConfig[variant] || variantConfig.danger;

  return createPortal(
    <div
      className="fixed inset-0 z-[100020] flex items-center justify-center modal-backdrop p-4 animate-in fade-in duration-100 select-none"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !isLoading) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      {/* Clean Desktop Confirmation Dialog */}
      <div className="bg-bg-card border border-border-color shadow-2xl w-full max-w-md text-text-primary flex flex-col rounded-none animate-in zoom-in-95 duration-100 overflow-hidden">
        {/* Title Bar */}
        <div className="flex items-center justify-between px-4 py-3 bg-bg-sidebar border-b border-border-color">
          <div className="flex items-center gap-2.5">
            {current.icon}
            <h3 className="text-sm font-semibold text-text-primary tracking-tight">
              {title}
            </h3>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="text-text-muted hover:text-text-primary p-1 transition-colors cursor-pointer rounded-none disabled:opacity-50"
            title="Cancel (Esc)"
          >
            <X size={15} />
          </button>
        </div>

        {/* Dialog Body */}
        <div className="p-5 flex flex-col gap-2 text-xs text-text-secondary leading-relaxed font-sans">
          {typeof message === "string" ? <p>{message}</p> : message}
        </div>

        {/* Action Controls */}
        <div className="px-4 py-3 bg-bg-sidebar/50 border-t border-border-color flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="default"
            onClick={onClose}
            disabled={isLoading}
            className="rounded-none text-xs px-3.5 h-8 cursor-pointer font-sans"
          >
            {cancelText}
          </Button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-4 h-8 rounded-none text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${current.btnClass}`}
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
