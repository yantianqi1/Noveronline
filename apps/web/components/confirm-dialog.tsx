"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

type ConfirmDialogProps = {
  cancelLabel: ReactNode;
  children?: ReactNode;
  confirmLabel: ReactNode;
  description: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
  open: boolean;
  title: ReactNode;
  tone?: "default" | "danger";
};

/**
 * Accessible confirm surface: focus moves into the dialog and returns on close.
 */
export function ConfirmDialog({
  cancelLabel,
  children,
  confirmLabel,
  description,
  onCancel,
  onConfirm,
  open,
  title,
  tone = "default",
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (open) {
      previousFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      if (!dialog.open) {
        dialog.showModal();
      }
      confirmRef.current?.focus();
      return;
    }

    if (dialog.open) {
      dialog.close();
    }
    previousFocusRef.current?.focus();
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <dialog
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      className="confirm-dialog"
      data-tone={tone}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      ref={dialogRef}
    >
      <form
        className="confirm-dialog-form"
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm();
        }}
      >
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        {children}
        <div className="confirm-dialog-actions">
          <button className="submit-button" data-tone="secondary" onClick={onCancel} type="button">
            {cancelLabel}
          </button>
          <button className="submit-button" data-tone={tone === "danger" ? "danger" : "primary"} ref={confirmRef} type="submit">
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
