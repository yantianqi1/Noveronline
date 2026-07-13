"use client";

import { useState, type ReactNode } from "react";
import { ConfirmDialog } from "./confirm-dialog";
import { SubmitButton } from "./submit-button";

type ConfirmSubmitButtonProps = {
  cancelLabel: ReactNode;
  confirmDescription: ReactNode;
  confirmLabel: ReactNode;
  confirmTitle: ReactNode;
  idleLabel: ReactNode;
  pendingLabel?: ReactNode;
  tone?: "primary" | "secondary" | "danger";
};

/**
 * Submit control that requires explicit confirm for destructive actions.
 * Uses native form requestSubmit after confirmation so server actions still work.
 */
export function ConfirmSubmitButton({
  cancelLabel,
  confirmDescription,
  confirmLabel,
  confirmTitle,
  idleLabel,
  pendingLabel,
  tone = "danger",
}: ConfirmSubmitButtonProps) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<HTMLFormElement | null>(null);

  return (
    <>
      <button
        className="submit-button"
        data-tone={tone}
        onClick={(event) => {
          event.preventDefault();
          setForm(event.currentTarget.form);
          setOpen(true);
        }}
        type="button"
      >
        {idleLabel}
      </button>
      <ConfirmDialog
        cancelLabel={cancelLabel}
        confirmLabel={confirmLabel}
        description={confirmDescription}
        onCancel={() => setOpen(false)}
        onConfirm={() => {
          setOpen(false);
          form?.requestSubmit();
        }}
        open={open}
        title={confirmTitle}
        tone={tone === "danger" ? "danger" : "default"}
      />
      {/* Hidden submit participates in useFormStatus when form is pending after confirm. */}
      <span className="sr-only" aria-hidden="true">
        <SubmitButton idleLabel={idleLabel} pendingLabel={pendingLabel} tone={tone} tabIndex={-1} />
      </span>
    </>
  );
}
