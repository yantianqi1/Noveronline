"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useFormStatus } from "react-dom";

type SubmitButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  idleLabel: ReactNode;
  pendingLabel?: ReactNode;
  tone?: "primary" | "secondary" | "danger";
  /** Client-owned submit flows that do not use form action status. */
  forcePending?: boolean;
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
  forcePending = false,
  ...rest
}: SubmitButtonProps) {
  const { pending } = useFormStatus();
  const busy = pending || forcePending;
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
