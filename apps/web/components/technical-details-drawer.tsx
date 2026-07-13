"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type TechnicalDetailsDrawerProps = {
  children: ReactNode;
  description?: ReactNode;
  label?: ReactNode;
  open?: boolean;
};

/**
 * Authorized technical diagnostics drawer.
 * Focus enters when opened and returns to the trigger on close.
 *
 * The dialog is portaled to document.body so dark side-rail ancestor styles
 * (light ink for admin chrome) cannot wash out paper-surface text.
 */
export function TechnicalDetailsDrawer({
  children,
  description,
  label = "Technical details",
  open: defaultOpen = false,
}: TechnicalDetailsDrawerProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [mounted, setMounted] = useState(false);
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) {
      return;
    }
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (open) {
      if (!dialog.open) {
        dialog.showModal();
      }
      closeRef.current?.focus();
      return;
    }
    if (dialog.open) {
      dialog.close();
    }
    triggerRef.current?.focus();
  }, [open, mounted]);

  const dialogNode = (
    <dialog
      aria-describedby={description ? descriptionId : undefined}
      aria-labelledby={titleId}
      className="technical-details-dialog"
      data-surface="paper"
      onCancel={(event) => {
        event.preventDefault();
        setOpen(false);
      }}
      ref={dialogRef}
    >
      <div className="technical-details-dialog-header">
        <div>
          <h2 id={titleId}>{label}</h2>
          {description ? <p id={descriptionId}>{description}</p> : null}
        </div>
        <button
          className="submit-button"
          data-tone="secondary"
          onClick={() => setOpen(false)}
          ref={closeRef}
          type="button"
        >
          Close
        </button>
      </div>
      <div className="technical-details-dialog-body">{children}</div>
    </dialog>
  );

  return (
    <div className="technical-details-drawer" data-open={open ? "true" : "false"}>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        className="technical-details-trigger submit-button"
        data-tone="secondary"
        onClick={() => setOpen(true)}
        ref={triggerRef}
        type="button"
      >
        <span>{label}</span>
        {description ? <small>{description}</small> : null}
      </button>
      {mounted ? createPortal(dialogNode, document.body) : null}
    </div>
  );
}
