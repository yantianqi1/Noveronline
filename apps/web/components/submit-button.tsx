"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useFormStatus } from "react-dom";

type SubmitButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  idleLabel: ReactNode;
  pendingLabel?: ReactNode;
  tone?: "primary" | "secondary" | "danger";
};

/**
 * Form submit control that disables while pending and exposes aria-busy.
 * Feedback must appear without silent double-submit.
 */
export function SubmitButton({
  className = "",
  disabled,
  idleLabel,
  pendingLabel,
  tone = "primary",
  type = "submit",
  ...rest
}: SubmitButtonProps) {
  const { pending } = useFormStatus();
  const busy = pending;
  const label = busy ? (pendingLabel ?? idleLabel) : idleLabel;

  return (
    <button
      {...rest}
      aria-busy={busy}
      className={["submit-button", className].filter(Boolean).join(" ")}
      data-tone={tone}
      disabled={disabled || busy}
      type={type}
    >
      {label}
    </button>
  );
}
